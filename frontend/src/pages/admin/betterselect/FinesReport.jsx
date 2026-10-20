// BetterSelect → Fines → Report: run the squad's fines for a period and take them
// away as a PDF, with the reason and note for each fine.
import { useState } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { downloadFinesReport, rangeText } from '../../../lib/finesReport'
import { Btn } from './ui'
import { Card, inputCls, money, shortDate, todayISO } from './finesUi'
import { Kpi } from './FinesOverview'

const isoDaysAgo = (n) => {
  const d = new Date(); d.setDate(d.getDate() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function FinesReport({ teamId, squadName }) {
  const toast = useToast()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [rep, setRep] = useState(null)
  const [busy, setBusy] = useState(false)

  const run = async (range = { from, to }) => {
    setBusy(true)
    try { setRep(await api.bsFinesReport(teamId, range)) } catch (e) { toast.error(e.message || 'Could not run the report') } finally { setBusy(false) }
  }
  const preset = (f, t) => { setFrom(f); setTo(t); run({ from: f, to: t }) }
  const pdf = async () => {
    setBusy(true)
    try {
      const club = await api.adminGetSettings().catch(() => ({}))
      await downloadFinesReport({ club, rep })
    } catch (e) { toast.error('Could not make the PDF: ' + e.message) } finally { setBusy(false) }
  }

  return (
    <div data-fines-report>
      <Card title="Fines report" sub={`Pick a period, run it, then download it as a PDF with every fine's reason and note.`}>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[12px] text-pb-faint">From
            <input type="date" value={from} max={todayISO()} onChange={(e) => setFrom(e.target.value)} className={`${inputCls} block mt-1`} aria-label="From" />
          </label>
          <label className="text-[12px] text-pb-faint">To
            <input type="date" value={to} max={todayISO()} onChange={(e) => setTo(e.target.value)} className={`${inputCls} block mt-1`} aria-label="To" />
          </label>
          <Btn variant="primary" onClick={() => run()} disabled={busy}>{busy ? 'Working…' : 'Run report'}</Btn>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          <Btn sm onClick={() => preset('', '')}>All time</Btn>
          <Btn sm onClick={() => preset(isoDaysAgo(30), '')}>Last 30 days</Btn>
          <Btn sm onClick={() => preset(isoDaysAgo(90), '')}>Last 90 days</Btn>
          <Btn sm onClick={() => preset(`${new Date().getFullYear()}-01-01`, '')}>This year</Btn>
        </div>
      </Card>

      {rep && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4" data-report-tiles>
            <Kpi label="Fines" value={rep.totals.count} hint={rangeText(rep)} />
            <Kpi label="Fined" value={money(rep.totals.fined)} />
            <Kpi label="Paid in" value={money(rep.totals.paid)} tone="var(--pb-positive)" />
            <Kpi label="Still to collect" value={money(rep.totals.owing_now)} hint="whole squad, to date" tone="var(--pb-amber)" />
          </div>
          <Card title="Every fine" sub="As it will appear in the PDF."
            right={<Btn variant="primary" onClick={pdf} disabled={busy || rep.totals.count === 0 && rep.payments.length === 0} data-download-pdf>Download PDF</Btn>}>
            {rep.sessions.length === 0 && <p className="text-sm text-pb-faint" data-report-empty>No fines in this period.</p>}
            {rep.sessions.map((s) => (
              <div key={s.date} className="mb-3 last:mb-0" data-report-session={s.date}>
                <div className="flex justify-between gap-3 text-[13px] font-semibold border-b pb-hairline pb-1 mb-1">
                  <span>{shortDate(s.date)}</span><span>{money(s.total)}</span>
                </div>
                {s.entries.map((e, i) => (
                  <div key={i} className="flex justify-between gap-3 text-[13px] py-0.5">
                    <span className="min-w-0"><b className="font-medium">{e.player}</b> · {e.reason}{e.note ? <span className="text-pb-faint"> · {e.note}</span> : null}</span>
                    <span className="shrink-0">{money(e.amount)}</span>
                  </div>
                ))}
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  )
}
