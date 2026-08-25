import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { MODULE } from '../../../lib/modules'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import { Button, SegButtons, StatCard, Caption, Empty } from '../../../components/admin/ui'
import ScreenIntro, { useScreenIntro, INTROS } from './intro'
import { useClubhouseData, clubhouseModules, money } from './data'

// Reports — one screen with a source selector, replacing a reports page per
// sub-module. The headline figures here come from the same roll-up every other
// screen reads, so a number can't quietly disagree with the one beside it; the
// detailed breakdowns still live on the source screens, which own them.

export default function ClubhouseReports() {
  const navigate = useNavigate()
  const { hasModule } = useAuth()
  const modules = clubhouseModules(hasModule)
  const { data, counts, loading } = useClubhouseData(modules)
  const intro = useScreenIntro('reports')

  const sources = [
    modules.fees && { key: 'money', label: 'Money', to: '/admin/fees/reports' },
    modules.merch && { key: 'stock', label: 'Stock', to: '/admin/merch/reports' },
  ].filter(Boolean)
  const [source, setSource] = useState(sources[0]?.key || 'money')
  const current = sources.find(s => s.key === source)

  if (intro.showing) {
    return (
      <BetterClubhouseLayout title="Reports"
        actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.reports} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterClubhouseLayout>
    )
  }

  const s = data?.fees?.summary || {}

  return (
    <BetterClubhouseLayout
      title="Reports"
      caption={data?.season ? data.season.name : 'This season'}
      onHelp={intro.reopen}
      // Which source you are reading sits on the title line, centred, in
      // Committee's own segmented control — one source at a time, which is
      // exactly what that control is for.
      tabs={sources.length > 1 && (
        <SegButtons value={source} onChange={setSource}
          tabs={sources.map(x => ({ key: x.key, label: x.label }))} />
      )}
      actions={current && (
        <Button variant="primary" onClick={() => navigate(current.to, { state: { skipIntro: true } })}>
          Full {current.label.toLowerCase()} report
        </Button>
      )}
    >
      <div className="max-w-[74rem]">
        {sources.length === 0 ? (
          <Empty>There is nothing to report on until the club holds a module that produces numbers.</Empty>
        ) : loading && !data ? <Empty>Reading the club…</Empty> : source === 'money' ? (
          <>
            <Caption>Money, this season</Caption>
            <div className="grid gap-2 mt-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              <StatCard value={money(s.total_payable)} label="Billed" detail={`Across ${counts.people} ${counts.people === 1 ? 'person' : 'people'}.`} />
              <StatCard value={money(s.total_paid)} label="Taken" accent />
              <StatCard value={money(s.total_outstanding)} label="Outstanding" ink={counts.owing ? '#f5b542' : undefined}
                detail={counts.owing ? `${counts.owing} ${counts.owing === 1 ? 'member owes' : 'members owe'}.` : 'Everyone is square.'} />
              <StatCard value={money(s.membership_outstanding)} label="Subs outstanding" />
              <StatCard value={money(s.match_fee_outstanding)} label="Match fees outstanding" />
              <StatCard value={money(s.credit)} label="In credit" ink={s.credit > 0 ? 'var(--pb-positive-ink)' : undefined} />
            </div>
          </>
        ) : (
          <>
            <Caption>Stock, right now</Caption>
            <div className="grid gap-2 mt-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              <StatCard value={money(counts.stockCost)} label="Stock at cost" accent />
              <StatCard value={money(data?.merch?.stock_value_retail)} label="Stock at retail" />
              <StatCard value={counts.units.toLocaleString()} label="Units on hand" />
              <StatCard value={money(counts.kitOwed)} label="Issued kit unpaid" ink={counts.kitOwed > 0 ? '#f5b542' : undefined}
                detail="Charged to members' accounts." />
              <StatCard value={counts.reorder} label="Lines to reorder" ink={counts.reorder ? '#f5b542' : undefined} />
              <StatCard value={counts.expiring} label="Expiring soon" ink={counts.expiring ? '#f5b542' : undefined} />
            </div>
          </>
        )}
      </div>
    </BetterClubhouseLayout>
  )
}
