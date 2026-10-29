# Hyperframes Composition Brief: BetterCricket Player Cards (Applecross as the example club)

## Objective
A 25s landscape launch-style video for the new Player Cards in BetterCricket, using real Applecross Cricket Club data.

## Output
- Composition: `brag-output-2026-10-29-045309/composition/` (single root `index.html`, built by a script from the real card components)
- Video: `brag-output-2026-10-29-045309/brag.mp4`, 1920x1080, 30fps, 50s (half speed)

## Source material
- Card faces rebuilt from `frontend/src/components/cards/CardFaces.jsx`, `cardTheme.js`, `PackOpening.jsx`, `CardGallery.jsx`, `SwapsPanel.jsx`
- Club: Applecross Cricket Club (`/api/clubs/applecross`): accent `#ff0000`, club display font (Montserrat Bold), badge
- Players, photos and career stats: Applecross's public player and leaderboard endpoints. Special cards from the stats feed and the club honour board
- Copy used verbatim from the app: "Welcome to the club", "Fresh this week", "Earned with the bat", "Earned with the ball", "Three in three", "A hundred. Take a bow", "A gift from your club", "wants to swap with you", "You would get", "You give", "Collected"

## Creative direction
- Tone: default, trading-card unboxing, dark stage, foil light
- Hook: wall of real cards, "EVERY PLAYER GETS A CARD."
- Outro: "Every player. Every pack. Your club's own cards."

## Scenes
1. Every player (0-2s)
2. Packs for everything, then the club designs its own pack (2-7s)
3. The pull: tear, Common, Rare, Epic, Legendary, Special (7-14s)
4. The card book: chips, grey slots, a special card held up and turned (14-17.5s)
5. Swaps: request, Accept click, cards land (17.5-21s)
6. Cards change to the club's colours, then end card (21-25s)

## Audio
- Music: happy-beats-business-moves-vol-1 (120 BPM), started at its first beat, fades over the last 1.5s
- Audio-reactive: the stage glow follows the bed's RMS (baked per frame from ffmpeg-decoded audio)
- SFX: card slides, pack-open, soft impacts on flips, bell on the Legendary and the end card, clicks on Accept
- Beat-locked: Accept click at 19.02s; pack-per-beat at 2.02 + 0.5n
