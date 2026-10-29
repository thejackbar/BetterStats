# Brag Plan: BetterCricket Player Cards (Applecross Cricket Club)

## What is this app?
BetterCricket gives every player at a club a collectable trading card built from their real career stats, with packs to open, a card book to fill and swaps with team-mates.

## The angle
This is a BetterCricket ad; Applecross is the demo club, and every card in the video is a real Applecross player with their real career numbers (Ramon Fletcher's 711 wickets, Rob Wilton's 9,247 runs, Pratik Bhave's 153). The pitch is "this is your club's own footy-card moment": every player, every pack, nothing paid. The pack opening is the centrepiece. It is the one thing a viewer can't get from a stats page.

## Hook (first 2-3 seconds)
Wall of Applecross cards slams in, then "EVERY PLAYER GETS A CARD." in the club's red. Real faces, real figures, the card frame shining.

## Key moments (the middle)
- **Packs for everything, built by the club**: Starter, Weekly, Runs, Wickets, Hat-trick, Century packs arrive one by one (the stars rise with the achievement). Then the club customises: a "Premiers Pack" in Applecross red with the club badge, quality stars climbing from Standard to Legendary. The line: "Your club designs the packs."
- **A pack opening**: sealed Weekly pack shakes, tears, flash, then five cards turn over lowest rarity first: Common (Brayden van Deuren), Rare (Abigail Cox), Epic (Grace Camarda), Legendary (Ramon Fletcher, rainbow foil), Special (Wade Ellie hat-trick, holo, rays). NEW badges. Best pull last.
- **The card book**: filter chips (All, Players, Specials, Club awards, Milestones, Centuries, Wickets), sort by Rarity, "Collected 14 / ..." progress bar, binder spread with a few grey slots, then a spare card and special card stacks.
- **Swaps**: "Jack Barendse wants to swap with you". Two cards each way, a click on Accept, the cards cross over.

## Outro / punchline
"Gotta collect 'em all." is the obvious one, so skip it. Land on: **"Every player. Every pack. Your club's own cards."** with the Applecross badge and BetterCricket Player Cards.

## User flow worth showing
Get a pack (earned by runs, wickets, hat-trick) -> tap it open and turn the cards over -> they land in the book (NEW) -> spot a double or want a card -> swap with a team-mate.

## Tone
- Preset: default (with app-store polish)
- Creative direction: a trading-card unboxing video, dark stage, foil light, crisp and postable, no sarcasm
- Interpretation: fast cuts and snappy card entrances, each key line holds long enough to read; the pack opening gets the biggest light and sound.

## Format: landscape - 1920x1080
## Duration: 90 seconds (paced slowly on request)

## Visual identity (from the project)
- Background: stage ground `#04070b` with a radial wash of `color-mix(#ff0000 30%, #0b1018)`, as the pack-opening overlay in `PackOpening.jsx`
- Accent: `#ff0000` (Applecross accent, from `/api/clubs/applecross`); club primary `#545454`
- Text: `#ffffff`, mono labels at 60-85% white
- Display font: Montserrat Bold (the club's uploaded display font, set italic caps like the real cards)
- Body font: Inter / JetBrains Mono (the card UI's own)
- Strongest visual element: the card faces (tier frames, foil, holo, slanted stat band) and the sealed foil pack

## Data used (all Applecross, pulled from the club's public pages)
- Career figures and photos: Ramon Fletcher, Rob Wilton, Angus Castley, Matthew Edwards, Chris Cooper, Isuri Wijesinghe, James Dockery, Wade Ellie, Jack Barendse, Len Blakey, Abigail Cox, Grace Camarda, Matt Campbell, Sheamus Byrne, Pratik Bhave and more
- Special cards: Pratik Bhave 153 off 256 v Kalamunda (1 Mar 2025); Chris Cooper 6/28 off 15 overs (14 Feb 2026); Wade Ellie hat-trick 2025/26; Matt Campbell 400 games; Len Blakey 5,000 career runs; Ramon Fletcher 600 career wickets; Matthew Edwards, Robert Pulley 1st XI Best & Fairest 2025/26 (honour board)
- Rarity numbers are worked out from the same blend the app uses, against a stand-in club pool

## Share copy (draft)
Every player at Applecross now has a card. Packs for runs, wickets and hat-tricks, a card book to fill, and swaps with your team-mates. BetterCricket Player Cards.

## Audio direction
- Role: warm rhythmic bed with card-game accents
- Music: `happy-beats-business-moves-vol-1` (120 BPM, beat every 0.5s), started at its first beat (3.0s into the file) so beats fall on 0.02 + 0.5n in the video
- Music treatment: enters at 0.0, steady under, fade out over the last 1.5s
- Music cue guidance: bundled preset read. Track strong beats from 16.02s onward (video 13.02s+). Lock the Legendary flip and the swap accept to strong cues (about 13.0s and 20.0s), and the end-card logo to 22.5s
- Audio-reactive treatment: subtle; music RMS/bass makes the stage glow behind the cards breathe. No waveform graphics
- SFX posture: moderate, motion-matched: card slides on card entrances, pack-open sound on the tear, soft impacts on the big flips, bell on the Legendary and the end card, clicks on the Accept press
- Audio-coupled moments: wall of cards (card-slide run), pack tear, five card flips in order, swap cards crossing
- Restraint rule: no SFX stacked on top of each other more than two deep; no sound without a visible cause

## Storyboard

### Scene 1 - Every player - 2.5s (0.0-2.5)
A wall of twelve real Applecross cards slides up in a tilted grid with a quick stagger, the Applecross badge top left. Headline "EVERY PLAYER GETS A CARD." slams in at 0.5s and holds to the cut. Small line: "Applecross Cricket Club . real career stats".
Sequential/interaction: yes - cards arrive in a staggered wave
Audio intent: instant energy
Audio-coupled idea: card-slide ticks on the first six arrivals
Transition mood: hard cut / push -> Scene 2

### Scene 2 - Packs - 5.0s (2.5-7.5)
Left: label "PACKS FOR EVERYTHING". Six packs rise one by one (Starter, Weekly, Runs, Wickets, Hat-trick, Century), each with its real tagline and stars. Each holds ~0.4s as the next arrives; the set then holds. At 5.0s the row slides off and one big pack morphs into the club's own design: "PREMIERS PACK", Applecross red, club badge, five stars, with a tiny designer panel (name, colour swatches, quality ladder Standard -> Legendary lighting up). Line: "Your club designs the packs."
Sequential/interaction: yes - packs arrive on the beat grid (every other beat for readability), quality ladder lights step by step
Audio intent: playful build
Audio-coupled idea: card-slide per pack, a rising click run on the ladder
Transition mood: wipe -> Scene 3

### Scene 3 - The pull - 7.0s (7.5-14.5)
Dark stage, sealed Weekly pack centred. "Tap to open" pulse, shake, tear, white flash. Five cards turn over in turn, lowest first: Common (van Deuren), Rare (Cox), Epic (Camarda, gold burst and shake), Legendary (Fletcher, rainbow, room dims), Special (Ellie hat-trick, holo, rays). A progress pip row and a rarity label under each. NEW badge on each. Final beat shows the five side by side as "Your pack".
Sequential/interaction: yes - simulated tap, five flips
Audio intent: tension and payoff
Audio-coupled idea: pack-open on the tear, a soft impact on each flip, bell on the Legendary (strong cue)
Transition mood: soft dissolve -> Scene 4

### Scene 4 - The card book - 4.0s (14.5-18.5)
Binder spread: header "Collected 14 / ..." (progress bar), filter chips cycling (All -> Specials -> Club awards), sort box "Rarity". Two pages of cards, with grey slots for players still to find. Stack of special cards on one slot. A card lifts and turns over to show the details back.
Sequential/interaction: yes - cards drop into slots one by one; a chip is "clicked"
Audio intent: satisfying
Audio-coupled idea: card-place per slot, click on the chip
Transition mood: slide -> Scene 5

### Scene 5 - Swaps - 4.0s (18.5-22.5)
Swap request panel: "Jack Barendse wants to swap with you". "You get" two cards, "You give" two cards, Accept button. Cursor presses Accept (strong cue), the cards cross over and a "Swap done" tick appears.
Sequential/interaction: yes - simulated click, cards cross
Audio intent: warm payoff
Audio-coupled idea: click on press, card-slide on crossing
Transition mood: hard cut -> Scene 6

### Scene 6 - End card - 2.5s (22.5-25.0)
Applecross badge, "EVERY PLAYER. EVERY PACK." then "Your club's own cards." and "BetterCricket Player Cards" lockup. Hold to the end with a short music fade.
Audio intent: resolve
Audio-coupled idea: bell on the lockup
Music mood for this video: upbeat
Audio summary: steady 120 BPM bed, card-game SFX on every card move, a bell on the Legendary and on the end card.


## Revision: slower cut (90s)
1. Intro slide: "Introducing BetterCricket Player Cards" (0-7s)
2. Every player gets a card (7-11.6s)
3. Packs, then the club designs its own pack (11.6-23.1s)
4. The pull: three cards only (Common, Rare, Legendary), slow flips, a gap between each (23.1-42.9s)
5. Card types: four rarity tiers with their odds (42.9-51s)
6. Card types: special cards, six kinds (51-61s)
7. Card book, with the century card held up and turned over, long hold (61-71.9s)
8. Swap (71.9-80s)
9. Cards change to the club's colours, then the BetterCricket end card (80-90s)
