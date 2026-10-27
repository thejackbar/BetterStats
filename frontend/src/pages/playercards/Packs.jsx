import { PackArt } from '../../components/cards/PackOpening'
import { PACKS } from '../../components/cards/cardTheme'
import PageHead from './PageHead'
import { PackBlock, weekdayLabel } from './Home'
import { usePC } from './context'

const WAYS = [
  ['starter', 'You start with two of these, so you can open a pack the day you arrive.'],
  ['weekly', null],
  ['runs', 'One for every 25 runs you score this season, in any grade.'],
  ['wickets', 'One for every 2 wickets you take this season.'],
  ['dismissals', 'One for every 2 dismissals (catches, run outs and stumpings) this season.'],
  ['duck', 'Out for a duck? Here is one, with the club\'s sympathy.'],
]

export default function Packs() {
  const { data, failed, club, accent, display } = usePC()
  if (failed) return <div className="text-sm text-pb-faint" data-cards-failed>Your packs could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-cards-loading>Loading your packs…</div>
  return (
    <div data-screen="packs">
      <PageHead title="Open packs" sub="Five cards a pack, and at least one Rare or better in every one. Anything you pull goes straight into your book." />
      <div className="rounded-2xl border pb-hairline bg-pb-surface p-5 mb-6"><PackBlock big /></div>
      <h2 style={{ font: `800 italic 22px ${display}`, textTransform: 'uppercase' }} className="mb-3">How packs arrive</h2>
      <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))' }} data-pack-ways>
        {WAYS.map(([src, line]) => (
          <div key={src} data-way={src} className="flex gap-4 items-center rounded-2xl border pb-hairline bg-pb-surface p-4">
            <PackArt source={src} club={club} accent={accent} display={display} width={54} />
            <div className="min-w-0">
              <div className="font-bold">{PACKS[src].label}</div>
              <div className="text-sm text-pb-dim mt-0.5">{src === 'weekly' ? `A fresh one every Monday. The next arrives ${weekdayLabel(data.week_resets_at)}.` : line}</div>
            </div>
          </div>
        ))}
      </div>
      <p className="text-sm text-pb-dim mt-5 max-w-prose">Packs you do not open keep waiting, except a weekly pack that is not opened by the end of its week. Every card is a real player or a real moment from the club's history. There are no paid packs.</p>
    </div>
  )
}
