# Composition Brief: BetterCricket Player Dashboard

- Composition: `composition/` (single root `index.html`, built from the real dashboard screenshots plus HTML mockups)
- Screens: the real front end (`frontend/src/pages/PublicAvailability.jsx` and `playerhome/*`) run locally with a stubbed API and captured in Chromium at 390x844, 2x
- Data: Applecross Cricket Club branding and badge; Jack Barendse's real 2025/26 season figures from the club's public stats; demo fixtures, fees, votes, fantasy and training; demo contact details
- Voiceover: generated with VoiceStudio's OmniVoice engine on CPU (`omnivoice.models.omnivoice.OmniVoice`, voice design then a reusable voice clone prompt so every line has the same voice); lines in `voiceover-script.json`
- Music: happy-beats-business-moves-vol-1, ducked under the voice
- Scene timings are derived from the length of each generated voice line
