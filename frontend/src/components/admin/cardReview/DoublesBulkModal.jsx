import { useEffect, useState } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { PbSpinner } from '../../../lib/presskit'
import { Button, Note } from '../ui'
import { fmtDate, matchPageUrl } from './shared'

const WHAT = { relink: 'Move to the right match', ca: 'Link' }

// The confirmation before fixing every strong double at once: what it will do, a sample to look at,
// and one batch that can be undone from the Card review overview.
export default function DoublesBulkModal({ onClose, onDone }) {
  const toast = useToast()
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.cardReviewDoublesBulkPreview().then(setPreview).catch(e => setError(e.message)) }, [])

  async function apply() {
    setBusy(true)
    try {
      const r = await api.cardReviewDoublesBulk()
      toast.success(`${r.relinked} links moved to the right match, ${r.linked} pairs linked${r.skipped?.length ? `, ${r.skipped.length} skipped` : ''}`)
      onDone()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const total = preview ? preview.relink + preview.ca : 0
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/65 p-4 sm:pt-16" role="dialog" aria-modal="true" aria-label="Fix the strong doubles" data-testid="doubles-bulk-modal">
      <div className="w-full max-w-[860px] rounded-xl border border-pb-hairline2 bg-pb-surface p-5 sm:p-6 shadow-2xl">
        {!preview && !error && <PbSpinner message="Counting…" />}
        {error && <Note toneKey="block">{error}</Note>}
        {preview && (
          <>
            <h2 className="font-display text-[20px] font-semibold text-pb-text">Fix the strong doubles?</h2>
            <p className="mt-1.5 text-[13px] text-pb-dim">
              Only strong matches are included: the cards agree on most of their batters. Likely and possible matches are left for you to look at one by one.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-pb-hairline bg-pb-surface2 p-4" data-testid="bulk-relink">
                <div className="text-[22px] font-semibold text-pb-text">{preview.relink.toLocaleString()}</div>
                <div className="text-[13px] text-pb-dim">club scorecards linked to the wrong game. Each link moves to the game that matches the card.</div>
              </div>
              <div className="rounded-lg border border-pb-hairline bg-pb-surface2 p-4" data-testid="bulk-link">
                <div className="text-[22px] font-semibold text-pb-text">{preview.ca.toLocaleString()}</div>
                <div className="text-[13px] text-pb-dim">club scorecards with no link, linked to the game that matches. A game freed by a moved link is checked again afterwards.</div>
              </div>
            </div>
            <p className="mt-3 text-[12.5px] text-pb-dim">
              Nothing is deleted. Both cards of every match stay stored. A moved link keeps showing whichever card it shows now. A newly linked pair shows the Cricket Australia card when the batters agree, as any paired match does, and can be switched in the other steps. The whole batch is recorded and can be undone from Card review.
            </p>
            {preview.sample.length > 0 && (
              <div className="mt-4 overflow-x-auto rounded-lg border border-pb-hairline">
                <table className="w-full text-[12.5px]">
                  <tbody>
                    {preview.sample.map(r => (
                      <tr key={r.key} className="border-b border-pb-hairline last:border-0">
                        <td className="px-3 py-2 whitespace-nowrap">{WHAT[r.kind]}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmtDate(r.date)}</td>
                        <td className="px-3 py-2">{r.a.grade} v {r.a.opposition}</td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          <a className="text-pb-accent-ink hover:underline mr-3" href={matchPageUrl(r.a.id)} target="_blank" rel="noreferrer">Club card</a>
                          <a className="text-pb-accent-ink hover:underline" href={matchPageUrl(r.b.id)} target="_blank" rel="noreferrer">Cricket Australia</a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <label className="mt-4 flex items-start gap-2 text-[13px] text-pb-text">
              <input type="checkbox" className="mt-0.5" checked={ack} onChange={e => setAck(e.target.checked)} data-testid="doubles-bulk-ack" />
              <span>I have looked at a few of the matches above.</span>
            </label>
            <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="primary" disabled={!ack || busy || total === 0} onClick={apply} data-testid="doubles-bulk-apply">
                {busy ? 'Fixing…' : `Fix ${total.toLocaleString()}`}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
