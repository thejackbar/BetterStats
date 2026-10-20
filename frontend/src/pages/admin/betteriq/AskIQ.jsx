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

// Render **bold** as actual bold (the model uses markdown bold for its picks).
// Plain text + <strong> only, so it's injection-safe; newlines are kept by the
// pre-wrap container around it.
function renderRich(text) {
  return String(text || '').split(/\*\*/).map((seg, i) => (i % 2 === 1 ? <strong key={i}>{seg}</strong> : seg))
}

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

// Buttons for a question BetterIQ put back to the user. Only the latest set is
// live; an earlier one stays on screen, greyed, as the record of what was asked.
// Typing a reply in the ask bar answers it just as well.
function ClarifyChoices({ options, live, onPick }) {
  return (
    <div className="flex flex-wrap gap-2 mt-3" role="group" aria-label="Choose an answer">
      {options.map(o => (
        <button key={o.label} type="button" disabled={!live} onClick={() => onPick(o)}
          className="text-left text-[13px] font-medium transition min-w-0"
          style={{ padding: '8px 14px', borderRadius: 10, color: 'var(--pb-text)',
            background: 'color-mix(in srgb, var(--pb-accent) 14%, var(--pb-surface2))',
            border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)',
            opacity: live ? 1 : 0.45, cursor: live ? 'pointer' : 'default' }}
          onMouseEnter={e => { if (live) e.currentTarget.style.borderColor = 'var(--pb-accent)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export default function AskIQ() {
  const [q, setQ] = useState('')
  const [thread, setThread] = useState([])   // { question, answer?, error?, loading? }
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [thread])

  // `display` is what the bubble shows when a button's label stands in for the
  // fuller instruction it sends ("3rd Grade" shown, "Use 3rd Grade" sent).
  const ask = async (question, display) => {
    const text = (question ?? q).trim()
    if (!text || busy) return
    // Carry the answered turns so far so a follow-up keeps its subject. `sent` is
    // what the server was actually asked; `clarified` tells it the last turn was a
    // question back to the user, so it answers this time instead of asking again.
    const history = thread.filter(x => x.answer && !x.error)
      .map(x => ({ question: x.sent || x.question, answer: x.answer, clarified: !!x.clarify }))
    setQ(''); setBusy(true)
    setThread(t => [...t, { question: display || text, sent: text, loading: true }])
    const finish = (patch) => setThread(t => t.map((x, i) => (i === t.length - 1 ? { question: display || text, sent: text, ...patch } : x)))
    try {
      const r = await api.iqAsk(text, history)
      if (r?.available) finish({ answer: r.answer, clarify: r.clarify || null })
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
                  : <Bubble side="a">
                      <span className="whitespace-pre-wrap">{renderRich(x.answer)}</span>
                      {x.clarify?.options?.length > 0 && (
                        <ClarifyChoices options={x.clarify.options} live={i === thread.length - 1 && !busy}
                          onPick={o => ask(o.value || o.label, o.label)} />
                      )}
                    </Bubble>}
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
            placeholder={thread[thread.length - 1]?.clarify && !busy ? 'Pick one, or type a reply…' : 'Ask about your record, form, par scores, batting order…'}
            className="flex-1 resize-none outline-none bg-transparent px-2.5 py-2 text-[14px]"
            style={{ color: 'var(--pb-text)', maxHeight: 120 }} />
          <Btn variant="primary" icon="bolt" disabled={busy || !q.trim()} onClick={() => ask()}>{busy ? 'Asking…' : 'Ask'}</Btn>
        </div>
      </div>
    </IQLayout>
  )
}
