# Composition Brief: BetterCricket Player Dashboard

- Composition: `composition/` (single root `index.html`, built from the real dashboard screenshots plus HTML mockups)
- Screens: the real front end (`frontend/src/pages/PublicAvailability.jsx` and `playerhome/*`) run locally with a stubbed API and captured in Chromium at 390x844, 2x. Five full-page states of the dashboard (start, Available tapped, See more games, first fixture open, second fixture open) so the phone can scroll once from top to bottom.
- Page order in the video: availability, fixtures, selection, fees, voting, stats, Fantasy, Player Cards. In the real app Player Cards sits second; it is moved to the end here (capture-only CSS) so the scroll never goes back up.
- Data: Applecross Cricket Club branding and badge; Jack Barendse's real 2025/26 season figures from the club's public stats; demo fixtures, fees, votes, fantasy and training; demo contact details
- Colours: BetterCricket green `#24c484` on near-black, white text. The only red on screen is inside the real dashboard screenshots (Applecross club accent).
- Audio: music only (happy-beats-business-moves-vol-1, steady under, fade out over the last 3s) plus soft taps, card slides and a bell on the end card. No voiceover.
- Scene changes are slow dissolves (0.7s out, short dark gap, 0.7s in). No wipes or colour flashes.
- Branding: persistent BetterCricket logo bug (scenes 2 to 7), green progress bar along the bottom, green phone rim, faint logo watermark, BetterCricket-led end card with betterat.cricket.
