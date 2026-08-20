import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import { Caption, StatCard, StatReadout, AttentionRow, Button, Empty } from '../../../components/admin/ui'
import { PbSpinner } from '../../../lib/presskit'
import { useClubhouseData, clubhouseModules, money } from './data'

// Today — the front door of BetterAdmin, replacing four separate module
// home pages (BetterFees had none, BetterComms opened on a list, BetterMerch
// had an overview, BetterClubManager had its own Today).
//
// It aggregates across money, people, stock and comms, and every count it shows
// is the same number the sidebar badge and the destination screen show, because
// all three read `useClubhouseData`. Nothing here is authored: a row that has
// nothing to say is not rendered, so an on-top club sees a short page rather
// than a wall of zeroes.

const fmtDate = d => d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

export default function ClubhouseToday() {
  const navigate = useNavigate()
  const { hasModule } = useAuth()
  const modules = clubhouseModules(hasModule)
  const { data, counts, loading } = useClubhouseData(modules)

  // Deep links skip the destination's introduction — the officer already said
  // what they wanted by pressing the button.
  const go = (to, state) => navigate(to, { state: { skipIntro: true, ...state } })

  const alerts = data?.merch?.alerts || {}
  const rows = []

  if (counts.owing > 0) {
    rows.push({
      key: 'owing', tone: 'block', count: counts.owing, area: 'Money',
      title: `${counts.owing === 1 ? 'A member owes' : `${counts.owing} members owe`} money`,
      detail: `${money(counts.owed)} outstanding across subs and match fees${counts.kitOwed > 0 ? `, plus ${money(counts.kitOwed)} of issued kit` : ''}.`,
      actions: [
        { label: 'Open accounts', primary: true, to: '/admin/fees' },
        modules.comms && { label: `Email these ${counts.owing}`, to: '/admin/comms/segments', state: { segment: 'owing' } },
      ],
    })
  }

  if (counts.reorder > 0) {
    rows.push({
      key: 'reorder', tone: 'warn', count: counts.reorder, area: 'Stock',
      title: `${counts.reorder === 1 ? 'A line is' : `${counts.reorder} lines are`} at or below the reorder point`,
      detail: (alerts.low_stock || []).slice(0, 3).map(a => a.product || a.name).filter(Boolean).join(', ') || 'Check the inventory before the next order goes in.',
      actions: [{ label: 'Open inventory', primary: true, to: '/admin/merch/stock' }],
    })
  }

  if (counts.expiring > 0) {
    rows.push({
      key: 'expiring', tone: 'warn', count: counts.expiring, area: 'Stock',
      title: `${counts.expiring === 1 ? 'A line expires' : `${counts.expiring} lines expire`} soon`,
      detail: 'Canteen and bar stock past its date cannot be sold.',
      actions: [{ label: 'Open inventory', to: '/admin/merch/stock' }],
    })
  }

  if (counts.serviceDue > 0) {
    rows.push({
      key: 'service', tone: 'warn', count: counts.serviceDue, area: 'Club · Stock',
      title: `${counts.serviceDue === 1 ? 'A piece of gear is' : `${counts.serviceDue} pieces of gear are`} due for service`,
      detail: 'Equipment with a service or replacement date that has come around.',
      actions: [{ label: 'Open equipment', to: '/admin/merch/equipment' }],
    })
  }

  if (counts.drafts > 0) {
    rows.push({
      key: 'drafts', tone: 'calm', count: counts.drafts, area: 'Comms',
      title: `${counts.drafts === 1 ? 'A draft email is' : `${counts.drafts} draft emails are`} waiting`,
      detail: 'Written but never sent.',
      actions: [{ label: 'Open emails', to: '/admin/comms' }],
    })
  }

  if (counts.needsTier > 0) {
    rows.push({
      key: 'tier', tone: 'calm', count: counts.needsTier, area: 'Money',
      title: `${counts.needsTier === 1 ? 'A member has' : `${counts.needsTier} members have`} no tier`,
      detail: 'Nothing is charged to a member until they sit on a membership tier.',
      actions: [{ label: 'Open accounts', to: '/admin/fees' }],
    })
  }

  const blocking = rows.filter(r => r.tone === 'block').length
  const caption = `${fmtDate(new Date())}${data?.season ? ` · ${data.season.name}` : ''}`

  const stats = (
    <>
      {modules.fees && <StatReadout value={money(counts.owed)} label="Owed to the club" ink="#f5b542" />}
      {modules.fees && <StatReadout value={counts.people.toLocaleString()} label="People" />}
      <StatReadout value={counts.needsYou} label="Need you" ink={counts.needsYou ? 'var(--pb-accent-ink)' : undefined} />
    </>
  )

  return (
    <BetterClubhouseLayout title="Today" caption={caption} stats={stats}>
      {loading && !data ? <PbSpinner message="Reading the club…" /> : (
        <div className="max-w-[74rem]">
          <Caption>
            {blocking > 0 ? 'Blocking first' : rows.length ? 'Worth a look' : 'All clear'}
          </Caption>
          <div className="flex flex-col gap-[7px] mt-2.5">
            {rows.length === 0 ? (
              <Empty>Nothing needs you. Subs are settled, stock is above its reorder points and no email is sitting in draft.</Empty>
            ) : rows.map(r => (
              <AttentionRow key={r.key} count={r.count} toneKey={r.tone} title={r.title} area={r.area} detail={r.detail}>
                {r.actions.filter(Boolean).map(a => (
                  <Button key={a.label} size="inline" variant={a.primary ? 'primary' : 'secondary'}
                    onClick={() => go(a.to, a.state)}>
                    {a.label}
                  </Button>
                ))}
              </AttentionRow>
            ))}
          </div>

          <Caption className="mt-7">The week ahead</Caption>
          <div className="grid gap-2 mt-2.5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
            {modules.fees && (
              <StatCard
                value={money(data?.fees?.summary?.total_paid)} label="Taken this season"
                detail={`${money(data?.fees?.summary?.total_payable)} billed across ${counts.people} ${counts.people === 1 ? 'person' : 'people'}.`}
                accent onClick={() => go('/admin/fees/payments')}
              />
            )}
            {modules.merch && (
              <StatCard
                value={money(counts.stockCost)} label="Stock at cost"
                detail={`${counts.units.toLocaleString()} units on hand.`}
                onClick={() => go('/admin/merch/stock')}
              />
            )}
            {modules.merch && (
              <StatCard
                value={money(counts.kitOwed)} label="Issued kit unpaid"
                detail="Charged to members' accounts, not a separate ledger."
                ink={counts.kitOwed > 0 ? '#f5b542' : undefined}
                onClick={() => go('/admin/fees')}
              />
            )}
            {modules.comms && (
              <StatCard
                value={(data?.campaigns || []).length} label="Emails this season"
                detail={counts.drafts ? `${counts.drafts} still in draft.` : 'None waiting in draft.'}
                onClick={() => go('/admin/comms')}
              />
            )}
          </div>
        </div>
      )}
    </BetterClubhouseLayout>
  )
}
