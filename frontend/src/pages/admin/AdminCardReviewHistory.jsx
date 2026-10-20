import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import { PbSpinner } from '../../lib/presskit'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { Button, Badge, Note, SegGroup, SegItem } from '../../components/admin/ui'
import { FindLink } from '../../components/admin/cardReview/MatchFilters'
import { fmtDate } from '../../components/admin/cardReview/shared'

const PAGE = 50

const when = iso => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

// Every change anyone has made in Card review, newest first, each with its undo. One place to put
// right a wrong click, whichever page it was made on. Only the newest change to a card can be undone
// (an older one would undo the wrong thing); after that, the one before it becomes available.
export default function AdminCardReviewHistory() {
  const toast = useToast()
  const [only, setOnly] = useState(false)
  const [rows, setRows] = useState([])
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const seq = useRef(0)

  const load = useCallback((add = false, offset = 0) => {
    const mine = ++seq.current
    setLoading(true)
    api.cardReviewHistory({ only: only ? 'undoable' : undefined, limit: PAGE, offset })
      .then(r => { if (mine !== seq.current) return; setRows(prev => (add ? [...prev, ...r.rows] : r.rows)); setMore(r.more); setError(null) })
      .catch(e => { if (mine === seq.current) setError(e.message) })
      .finally(() => { if (mine === seq.current) setLoading(false) })
  }, [only])
  useEffect(() => { load(false, 0) }, [load])

  async function undo(r) {
    setBusy(r.id)
    try {
      if (r.can === 'restore') {
        const res = await api.cardReviewDoubleRestore(r.match_id, r.other_id, r.other_kind || 'ca')
        toast.success(res.relinked ? 'The link is back' : 'Put back: the pair is offered again in Possible doubles')
      } else {
        await api.cardReviewUndo(r.match_id)
        toast.success('Undone')
      }
      load(false, 0)
    } catch (e) { toast.error(e.message) } finally { setBusy(null) }
  }

  return (
    <BetterStatsLayout
      title="Recent changes"
      caption="Everything changed in Card review"
      actions={<div className="flex flex-wrap gap-2"><FindLink filters={{}} /><Button as={Link} to="/admin/card-review" size="sm">Back to Card review</Button></div>}
    >
      <p className="max-w-[760px] text-[13.5px] text-pb-dim mb-4">
        Every switch, link, moved link, unlink and "different matches" answer made in Card review, newest first. Anything that can still be
        undone has a button. Only the newest change to a card can be undone, so if a card was changed twice, undo the later one first.
        A bulk switch or bulk fix is undone as a batch from the Card review overview.
      </p>
      <div className="mb-4">
        <SegGroup>
          <SegItem active={!only} onClick={() => setOnly(false)} data-testid="h-all">All changes</SegItem>
          <SegItem active={only} onClick={() => setOnly(true)} data-testid="h-undoable">Can be undone</SegItem>
        </SegGroup>
      </div>
      {error && <Note toneKey="block">{error}</Note>}
      {loading && rows.length === 0 && <PbSpinner message="Loading the changes…" />}
      {!loading && !error && rows.length === 0 && <Note toneKey="calm">{only ? 'Nothing can be undone.' : 'No changes have been made in Card review yet.'}</Note>}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-pb-hairline bg-pb-surface">
          <table className="w-full text-[13px]" data-testid="history-table">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-[0.1em] text-pb-faint">
                <th className="px-4 py-2.5 font-normal">When</th>
                <th className="px-3 py-2.5 font-normal">Who</th>
                <th className="px-3 py-2.5 font-normal">Match</th>
                <th className="px-3 py-2.5 font-normal">What changed</th>
                <th className="px-3 py-2.5 font-normal">Now</th>
                <th className="px-3 py-2.5 font-normal" />
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t border-pb-hairline align-top" data-testid="change" data-id={r.id} data-can={r.can || ''}>
                  <td className="px-4 py-2.5 whitespace-nowrap font-mono text-[12px] text-pb-dim">{when(r.at)}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap">{r.by || ''}{r.bulk && <span className="ml-1.5"><Badge toneKey="calm">batch</Badge></span>}</td>
                  <td className="px-3 py-2.5">
                    <div className="text-pb-text">{r.grade || 'No grade'} v {r.opposition || '—'}</div>
                    <div className="font-mono text-[11.5px] text-pb-faint">
                      {fmtDate(r.date)}{r.season ? ` · ${r.season}` : ''}
                      {r.match_id && r.linked_now && <> · <Link className="underline" to={`/admin/card-review/match/${r.match_id}`}>compare</Link></>}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-pb-text">{r.what}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap text-[12px]">
                    {r.undone_at ? <Badge toneKey="calm">Undone {when(r.undone_at)}</Badge>
                      : r.can ? <Badge toneKey="ok">Can be undone</Badge>
                        : r.action === 'refresh' ? <span className="text-pb-faint">Nothing to undo</span>
                          : <span className="text-pb-faint" title="A newer change was made to this card. Undo that one first.">Replaced by a newer change</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    {r.can && (
                      <Button size="sm" disabled={busy === r.id} onClick={() => undo(r)} data-testid="undo-change">
                        {r.can === 'restore' ? 'Put back' : 'Undo'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {more && (
        <div className="mt-4 text-center"><Button disabled={loading} onClick={() => load(true, rows.length)}>Show more</Button></div>
      )}
    </BetterStatsLayout>
  )
}
