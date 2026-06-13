/* BetterIQ — Ask: natural-language questions over the club's own data.
   Grounded answers from the record, approach and current form we already hold
   (POST /iq/ask). A specific-opponent question is steered to the scout. */
import { useState, useRef, useEffect } from 'react'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Card, Btn, Note, PageIntro, Icon, Initials, LoadingBar } from './ui'

const SUGGESTIONS = [
  'How do we go batting first versus chasing?',
  "Who's in the best form with the bat this season?",
  'What first-innings total usually wins us the game?',
  'Are we better at home or away?',
  'Who are our most economical bowlers this season?',
]

function Bubble({ side, children }) {
  const mine = side === 'q'
  return (
    <div className={`flex gap-3 ${mine ? 'flex-row-reverse' : ''}`}>
      <div className="shrink-0 mt-0.5">
        {mine
          ? <div className="flex items-center justify-center" style={{ width: 30, height: 30, borderRadius: 9, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)' }}><Icon name="player" size={15} className="text-pb-faint" /></div>
          : <Initials name="IQ" size={30} tone="accent" />}
      </div>
      <div className="max-w-[80%] px-3.5 py-2.5 text-[13.5px] leading-relaxed" style={{
        borderRadius: 14,
        background: mine ? 'var(--pb-surface2)' : 'color-mix(in srgb, var(--pb-accent) 10%, transparent)',
        border: `1px solid ${mine ? 'var(--pb-hairline)' : 'color-mix(in srgb, var(--pb-accent) 30%, transparent)'}`,
      }}>{children}</div>
    </div>
  )
}

export default function AskIQ() {
  const [q, setQ] = useState('')
  const [thread, setThread] = useState([])   // { question, answer?, error?, loading? }
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [thread])

  const ask = async (question) => {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setQ(''); setBusy(true)
    setThread(t => [...t, { question: text, loading: true }])
    const finish = (patch) => setThread(t => t.map((x, i) => (i === t.length - 1 ? { question: text, ...patch } : x)))
    try {
      const r = await api.iqAsk(text)
      if (r?.available) finish({ answer: r.answer })
      else finish({ error: r?.message || 'Natural-language answers aren\'t available right now.' })
    } catch (e) {
      finish({ error: e?.message || 'Something went wrong getting an answer.' })
    } finally { setBusy(false) }
  }

  const onKey = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }

  return (
    <IQLayout title="Ask BetterIQ" actions={thread.length ? <Btn variant="ghost" sm icon="refresh" onClick={() => setThread([])}>Clear</Btn> : null}>
      <PageIntro>Ask a plain question about your club and get an answer straight from the numbers you already hold: your record, how you win and lose, par scores and current form. For a specific opponent, use the Opposition scout.</PageIntro>

      {thread.length === 0 ? (
        <Card eyebrow="try one of these" title="What do you want to know?">
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => ask(s)}
                className="text-left text-[13px] px-3 py-2 transition" style={{ borderRadius: 10, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--pb-accent)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--pb-hairline2)' }}>
                {s}
              </button>
            ))}
          </div>
          <Note>Answers come from your own data and won't invent players or numbers. Limited to 20 questions an hour.</Note>
        </Card>
      ) : (
        <div className="space-y-4 mb-6">
          {thread.map((x, i) => (
            <div key={i} className="space-y-3">
              <Bubble side="q">{x.question}</Bubble>
              {x.loading
                ? <div className="max-w-[80%]"><div className="px-3.5 py-3" style={{ borderRadius: 14, background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' }}><LoadingBar label="Reading your data…" expectedMs={7000} /></div></div>
                : x.error
                  ? <Bubble side="a"><span style={{ color: 'var(--pb-amber)' }}>{x.error}</span></Bubble>
                  : <Bubble side="a"><span className="whitespace-pre-wrap">{x.answer}</span></Bubble>}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}

      {/* Ask bar */}
      <div className="sticky bottom-4 mt-2">
        <div className="flex items-end gap-2.5 p-2" style={{ borderRadius: 14, background: 'var(--pb-surface)', border: '1px solid var(--pb-hairline2)', boxShadow: 'var(--iq-card-shadow)' }}>
          <textarea
            value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} rows={1}
            placeholder="Ask about your record, form, par scores, batting order…"
            className="flex-1 resize-none outline-none bg-transparent px-2.5 py-2 text-[14px]"
            style={{ color: 'var(--pb-text)', maxHeight: 120 }} />
          <Btn variant="primary" icon="bolt" disabled={busy || !q.trim()} onClick={() => ask()}>{busy ? 'Asking…' : 'Ask'}</Btn>
        </div>
      </div>
    </IQLayout>
  )
}
