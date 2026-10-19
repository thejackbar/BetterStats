// Email the confirmed side: the captain's team sheet (with every player's mobile
// from their profile) and each selected player's "you're in". Only ever the
// CONFIRMED XI, never a draft, so it is disabled while the board has changes
// that are not confirmed yet. See backend services/selection_notify.py.
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Btn, Icon } from './ui'

const when = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export default function SendSide({ fixtureId, title, dirty, count, onClose }) {
  const toast = useToast()
  const [busy, setBusy] = useState(null)         // 'captain' | 'players' | null
  const [note, setNote] = useState('')
  const [result, setResult] = useState(null)     // the last answer, shown under the buttons
  const [notices, setNotices] = useState([])

  const loadNotices = useCallback(() => {
    api.bsSelectionNotices(fixtureId).then((r) => setNotices(r?.notices || [])).catch(() => {})
  }, [fixtureId])
  useEffect(() => { loadNotices() }, [loadNotices])

  const blocked = dirty || count === 0
  const send = async (to) => {
    setBusy(to)
    setResult(null)
    try {
      const r = await api.bsNotifySelection(fixtureId, to, to === 'players' ? note : null)
      setResult({ to, ...r })
      if (r.status === 'sent') toast.success(to === 'captain' ? `Sent to ${r.captain}` : `Emailed ${r.sent} player${r.sent === 1 ? '' : 's'}`)
      loadNotices()
    } catch (e) {
      setResult({ to, status: 'failed', message: e.message })
    } finally { setBusy(null) }
  }

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Email the side"
        className="w-[460px] max-w-full max-h-[90%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="px-[18px] py-4 border-b pb-hairline flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">Email the side</div>
            <div className="font-display font-bold text-[17px] mt-0.5 truncate">{title}</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1" aria-label="Close"><Icon name="close" size={18} /></button>
        </div>

        <div className="overflow-auto flex-1 pb-scroll p-[18px] space-y-5">
          {blocked && (
            <p className="text-[12.5px] text-pb-amber" data-testid="send-blocked">
              {count === 0 ? 'Pick and confirm a side first.' : 'You have changes that are not confirmed. Confirm the side first: only the confirmed XI is emailed.'}
            </p>
          )}

          <section>
            <h3 className="font-display font-semibold text-[14px]">The captain</h3>
            <p className="text-[12.5px] text-pb-dim mt-1">
              A team sheet in batting order with each player's mobile from their profile, so the captain does not have to look anyone up.
            </p>
            <div className="mt-2.5">
              <Btn variant="primary" sm icon="share" disabled={blocked || busy != null} onClick={() => send('captain')}>
                {busy === 'captain' ? 'Sending…' : 'Email the captain'}
              </Btn>
            </div>
          </section>

          <section>
            <h3 className="font-display font-semibold text-[14px]">The players</h3>
            <p className="text-[12.5px] text-pb-dim mt-1">
              Each selected player gets the match details and who their captain is. Under 18s are not emailed directly.
            </p>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={1000}
              placeholder="Add a note, for example what time to arrive (optional)"
              className="mt-2 w-full rounded-lg border border-pb-hairline2 bg-pb-surface2 px-3 py-2 text-[13px] text-pb-text" />
            <div className="mt-2">
              <Btn variant="primary" sm icon="share" disabled={blocked || busy != null} onClick={() => send('players')}>
                {busy === 'players' ? 'Sending…' : 'Email the players'}
              </Btn>
            </div>
          </section>

          {result && (
            <div role="status" data-testid="send-result"
              className="rounded-lg border border-pb-hairline bg-pb-surface2 px-3 py-2.5 text-[12.5px] text-pb-text space-y-1">
              {result.to === 'captain' ? (
                <>
                  <div className="font-semibold">
                    {result.status === 'sent' ? `Sent to ${result.captain}.` : `Not sent. ${result.message || ''}`}
                  </div>
                  {result.missing_phones?.length > 0 && (
                    <div className="text-pb-dim">No mobile on file for: {result.missing_phones.join(', ')}.</div>
                  )}
                  {result.template && <div className="text-pb-dim">Used your template: {result.template}.</div>}
                  {result.template_note && <div className="text-pb-amber" data-testid="template-note">{result.template_note}</div>}
                </>
              ) : (
                <>
                  <div className="font-semibold">
                    {result.sent ? `Emailed ${result.sent} player${result.sent === 1 ? '' : 's'}.` : `Nobody was emailed. ${result.message || ''}`}
                  </div>
                  {[...(result.failed || []), ...(result.skipped || [])].map((r, i) => (
                    <div key={i} className="text-pb-dim">{r.name}: {r.message}</div>
                  ))}
                  {result.template && <div className="text-pb-dim">Used your template: {result.template}.</div>}
                  {result.template_note && <div className="text-pb-amber" data-testid="template-note">{result.template_note}</div>}
                </>
              )}
            </div>
          )}

          {notices.length > 0 && (
            <section>
              <h3 className="font-mono text-[10px] uppercase tracking-wide3 text-pb-faint">Already sent for this match</h3>
              <ul className="mt-1.5 space-y-1" data-testid="send-history">
                {notices.slice(0, 8).map((n, i) => (
                  <li key={i} className="text-[12px] text-pb-dim flex flex-wrap gap-x-2">
                    <span className="text-pb-text">{n.kind === 'captain' ? 'Captain' : 'Player'}: {n.name || 'unknown'}</span>
                    <span>{n.status === 'sent' ? 'sent' : n.status === 'skipped' ? `skipped, ${n.message || n.reason || ''}` : `failed, ${n.message || n.reason || ''}`}</span>
                    <span>{when(n.at)}{n.automatic ? ', automatically' : ''}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
