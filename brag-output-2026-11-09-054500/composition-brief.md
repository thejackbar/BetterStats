# Composition Brief: BetterCricket Selection Whiteboard

- Composition: `composition/` (single root `index.html`)
- Screens: the real front end (`frontend/src/pages/admin/betterselect/AdminSelectionDraftTable.jsx`, route `/admin/betterselect/whiteboard`) run locally in Chromium at 1440 wide with the API stubbed. Stills and the drag clips are recorded at 2x so the camera can zoom in without going soft.
- Clips: `assets/clips/vA.mp4` (Hide unavailable) and `assets/clips/vB.mp4` (three drops, a swap, Confirm all) are real drags driven frame by frame with a cursor overlay, at 30fps.
- Camera: `#wbi` is zoomed and panned inside the fixed window by `cam()` in the timeline.
- Phone scene: reuses the Player Dashboard captures (name pick, PIN, Available tapped) for the availability link story.
- Data: fictional players, demo availability and lineups. Jack Barendse is the demo player. Applecross branding.
- Colours: BetterCricket green `#24c484` on near-black. Half-available colours on the cards are amber (W1) and sky blue (W2), set as club colours in the stub.
- Audio: music only, soft taps and card sounds. No voiceover.
- Scene changes are slow dissolves (0.7s out, short dark gap, 0.7s in).
