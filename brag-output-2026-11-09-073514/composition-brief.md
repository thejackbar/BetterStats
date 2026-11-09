# Composition Brief: BetterSocials

- Composition: `composition/` (single root `index.html`, built by a small script from the scene markup)
- Screens: the real BetterPosts editor (`frontend/src/pages/admin/AdminSocialPost.jsx`, route `/admin/social-post`) run locally in Chromium (1440x810, 2x) with the API stubbed. Real Applecross players and original hi-res photos; demo fixtures, results and scores.
- Clips: `assets/clips/*.mp4` are real clicks driven frame by frame with a cursor overlay at 30fps (fixtures, results, lineup, motm, milestones, totw, and a 1.3x sped-up customisation clip).
- Camera: `#wbi` is zoomed and panned inside the fixed window by `cam()` in the timeline.
- Stylised parts: the "hours back for volunteers" panel is HTML. The template wall and the fan of posts are real exported posters from the editor.
- Colours: BetterSocials pink `#EC4899` aurora (pink, violet, rose) on near-black, BetterCricket logo bug top right.
- Audio: music only, soft clicks and card sounds. No voiceover.
- Scene changes are slow dissolves (0.7s out, short dark gap, 0.7s in).
