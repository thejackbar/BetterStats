import { PackArt } from '../../components/cards/PackOpening'
import { PACKS } from '../../components/cards/cardTheme'
import PageHead from './PageHead'
import { PackBlock, weekdayLabel } from './Home'
import { usePC } from './context'

// How packs arrive, in groups. The odds behind each are in services/player_card_pack_kinds.py.
const GROUPS = [
  {
    id: 'regular', title: 'Every week and as you play', sub: 'The everyday packs. Rare or better is guaranteed in every one.',
    ways: [
      ['starter', 'You start with two of these, so you can open a pack the day you arrive.'],
      ['weekly', null],
      ['runs', 'One for every 25 runs you score this season, in any grade.'],
      ['wickets', 'One for every 2 wickets you take this season.'],
      ['dismissals', 'One for every 2 dismissals (catches, run outs and stumpings) this season.'],
      ['duck', 'Out for a duck? Here is one, with the club\'s sympathy.'],
    ],
  },
  {
    id: 'achievement', title: 'For what you do', sub: 'Hit a landmark and the pack that comes with it is stacked with Rare, Epic and Legendary cards. More stars, better cards.',
    ways: [
      ['century', 'A hundred in a game. Almost every card is Rare or better, with a real chance at a Legendary.'],
      ['five_for', 'Five wickets in an innings.'],
      ['hat_trick', 'Three wickets in three balls.'],
      ['fifty', 'A half century.'],
      ['milestone', 'A landmark card: a games, runs, wickets or dismissals milestone.'],
    ],
    note: 'These come for achievements from the day your club started using cards. Nothing is handed out for old history.',
  },
  {
    id: 'day', title: 'On the day', sub: 'Open your page on the day to pick one up. They wait for you once you have, but a missed day is a missed pack.',
    ways: [
      ['match_day', 'You are on the team sheet, or played a game, today.'],
      ['birthday', 'On your birthday, if the club has it on file.'],
      ['halloween', '31 October.'],
      ['melbourne_cup', 'The first Tuesday of November.'],
      ['christmas', '25 December.'],
      ['boxing_day', '26 December.'],
      ['new_year', '1 January.'],
      ['australia_day', '26 January.'],
      ['anzac_day', '25 April.'],
      ['mystery', 'Now and then, on a day nobody sees coming.'],
      ['event', 'Your club can also hand one out for a big day, like a Test match: one on each day it runs.'],
    ],
  },
]

export default function Packs() {
  const { data, failed, club, accent, display } = usePC()
  if (failed) return <div className="text-sm text-pb-faint" data-cards-failed>Your packs could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-cards-loading>Loading your packs…</div>
  return (
    <div data-screen="packs">
      <PageHead title="Open packs" sub="Five cards a pack, and at least one Rare or better in every one. Anything you pull goes straight into your book." />
      <div className="rounded-2xl border pb-hairline bg-pb-surface p-5 mb-6"><PackBlock big /></div>
      {GROUPS.map((g) => (
        <section key={g.id} data-pack-group={g.id} className="mb-7">
          <h2 style={{ font: `800 italic 22px ${display}`, textTransform: 'uppercase' }}>{g.title}</h2>
          <p className="text-sm text-pb-dim mt-0.5 mb-3 max-w-prose">{g.sub}</p>
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))' }} data-pack-ways>
            {g.ways.map(([src, line]) => (
              <div key={src} data-way={src} className="flex gap-4 items-center rounded-2xl border pb-hairline bg-pb-surface p-4">
                <PackArt source={src} club={club} accent={accent} display={display} width={88} />
                <div className="min-w-0">
                  <div className="font-bold">{PACKS[src].label}</div>
                  <div className="text-sm text-pb-dim mt-0.5">{src === 'weekly' ? `A fresh one every Monday. The next arrives ${weekdayLabel(data.week_resets_at)}.` : line}</div>
                </div>
              </div>
            ))}
          </div>
          {g.note && <p className="text-xs text-pb-faint mt-2 max-w-prose">{g.note}</p>}
        </section>
      ))}
      <p className="text-sm text-pb-dim mt-5 max-w-prose">Packs you do not open keep waiting, except a weekly pack that is not opened by the end of its week. Every card is a real player or a real moment from the club's history. There are no paid packs.</p>
    </div>
  )
}
