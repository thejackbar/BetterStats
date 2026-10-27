// How it works: where cards come from, the odds, what the rarity means, special cards, what a swap does, and who can see what.
import { TIERS } from '../../components/cards/cardTheme'
import PageHead from './PageHead'
import { usePC } from './context'

const ODDS = [['common', 'Common', '60 in 100', 'Rarity under 55'], ['rare', 'Rare', '28 in 100', 'Rarity 55 to 74'], ['epic', 'Epic', '10 in 100', 'Rarity 75 to 89'], ['legendary', 'Legendary', '2 in 100', 'Rarity 90 and up']]

function Section({ title, children, id }) {
  const { display } = usePC()
  return (
    <section data-how={id} className="rounded-2xl border pb-hairline bg-pb-surface p-5 mb-3">
      <h2 style={{ font: `800 italic 22px ${display}`, textTransform: 'uppercase', margin: '0 0 8px' }}>{title}</h2>
      <div className="text-[14.5px] leading-relaxed text-pb-dim max-w-prose [&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:mb-1">{children}</div>
    </section>
  )
}

export default function HowItWorks() {
  return (
    <div data-screen="how">
      <PageHead title="How it works" sub="Cards of the players in your club, built from the real scorebook." />
      <Section id="cards" title="The cards">
        <p>Every player in the club has a card with their career figures: matches, runs, batting average, wickets, bowling average and dismissals, across every grade. The cards update as the stats do. The number in the corner is the card's rarity, from 1 to 99, worked out from how the player's figures compare with the rest of the club.</p>
        <p>You always have your own card. Everyone else's you collect from packs and swaps.</p>
      </Section>
      <Section id="packs" title="Packs and the odds">
        <p>A pack has five cards. At least one is always Rare or better, and you never get the same card twice in one pack. Each card in a pack is drawn at these odds:</p>
        <div className="grid gap-2 my-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))' }}>
          {ODDS.map(([k, label, odds, rule]) => (
            <div key={k} data-odds={k} className="rounded-xl p-3 border" style={{ borderColor: (TIERS[k] || TIERS.common).glow }}>
              <div className="font-bold" style={{ color: (TIERS[k] || TIERS.common).ink }}>{label}</div>
              <div className="text-pb-text">{odds}</div>
              <div className="text-[12.5px]">{rule}</div>
            </div>
          ))}
        </div>
        <p>About one card in twenty is a special card instead (below). Those odds are for the everyday packs: the weekly pack every Monday, packs for your runs, wickets and dismissals this season, and a Duck Pack if it goes wrong.</p>
        <p>Some packs are better. A Match Day pack, a holiday pack (Halloween, the Melbourne Cup, Christmas and more), a birthday pack, a surprise drop and any big day your club schedules, like a Test match, give two Rare or better cards at least and lean towards the better tiers. A pack for something you did is better again: a half century, a landmark, a five-for or hat-trick, and best of all a century, which is nearly all Rare or better. You get those for achievements from the day your club started using cards, and the Packs screen shows the full list. There are no paid packs.</p>
      </Section>
      <Section id="specials" title="Special cards">
        <p>Special cards mark real moments: a century, a half century, a five wicket haul, a hat-trick, a debut, a games milestone (10, 50, 100 and on), a career milestone (every 1,000 runs, 200 wickets and 50 dismissals) and the club's awards. Each kind has its own colour. The player it is about starts with their debut card and their latest milestone card, and the rest turn up in packs.</p>
      </Section>
      <Section id="swaps" title="Swaps">
        <ul>
          <li>You can swap any card you hold, one or many at a time, for any cards another player holds. One card for four of theirs is fine.</li>
          <li>Your own card cannot be swapped away. Extra copies of it you have pulled can.</li>
          <li>Nothing moves until the other player says yes. They can say no, and you can cancel any time before.</li>
          <li>Requests lapse after 14 days. When someone accepts, every card in the request moves, or none of them do.</li>
          <li>The person asked can say yes, say no, or change it: pick different cards and send it back. The first request then ends and they decide on yours. A short note can go with any request.</li>
        </ul>
      </Section>
      <Section id="wishlist" title="Wish list, spares and emails">
        <ul>
          <li>Put any card on your wish list from Club cards. Only you can see the list. It shows who could swap you each card now, and you can ask them from there.</li>
          <li>A spare is a copy beyond the one you keep. The Spares page gathers them so you can offer several at once. If you switch a spare to open to offers, you will see how many players want that card, as a number, never as names.</li>
          <li>No emails are sent unless you ask for them. In Settings you can switch on an email for when someone asks you for a swap and for when a card on your wish list becomes available, and your club can switch the emails off for everyone.</li>
        </ul>
      </Section>
      <Section id="club" title="Sets, showcase and the collectors board">
        <ul>
          <li>A set is a group of cards you can work towards completing, such as every century at the club or a season's awards. Finishing one earns a banner and bragging rights, nothing more.</li>
          <li>Your showcase is up to six cards you hold, pinned for the club to see next to your name.</li>
          <li>The collectors board ranks everyone in the club, by how much of the club's set they hold. You can leave it in Settings. It counts different cards, never copies, so hoarding doubles does not help.</li>
          <li>This week lists what has happened in the club's cards lately. You can leave your name out of it in Settings.</li>
        </ul>
      </Section>
      <Section id="privacy" title="Who sees what">
        <ul>
          <li>Other players can see the cards you could swap and nothing else: not your packs, not your wish list, and not how many of a card you hold beyond what you could give.</li>
          <li>Club cards shows every card in the club and how many other players could swap you a copy. It never shows a person's whole collection.</li>
          <li>If you would rather not be in the cards, ask your club to hide you.</li>
        </ul>
      </Section>
    </div>
  )
}
