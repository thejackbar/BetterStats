# BetterPosts brag video

A 25 second, 1080x1920 launch video for BetterPosts, made with the `/brag` skill and Hyperframes. The sources live here so the video can be edited later. (The September 12-video set was built in a scratchpad that got wiped, and only the finished zips survived.)

- `brag-plan.md` and `composition-brief.md`: the plan, storyboard and the handoff brief.
- `composition/index.html`: the whole video, one paused GSAP timeline. Fonts, GSAP and the sound effects are vendored under `composition/`, so a render needs no network.
- `capture/capture.mjs`: shoots the real BetterPosts editor (API stubbed) and the real exported posts.
- `share-copy.txt`, `brag.jpg`: the caption and the poster (also baked in as frame 0 of the video).

## Rebuild

```bash
# 1. the editor
cd frontend && npm ci && npx vite --port 5199 --host 127.0.0.1 &

# 2. the real frames, into composition/assets/shots/
node docs/marketing-videos/betterposts/capture/capture.mjs docs/marketing-videos/betterposts/composition/assets/shots

# 3. the music (a copy of a bundled brag track)
mkdir -p docs/marketing-videos/betterposts/composition/assets/music
cp .claude/skills/brag/assets/music/happy-beats-business-moves-vol-11-by-ende-dot-app.mp3 docs/marketing-videos/betterposts/composition/assets/music/

# 4. check, then render
cd docs/marketing-videos/betterposts/composition
npx hyperframes@0.8.181 check
npx hyperframes@0.8.181 render --quality looks --output ../brag.mp4
```

Then pick the poster and bake it as frame 0 (brag skill, step 4).

## Sample data

The scoreline (Applecross 8/204 def. Balcatta 7/141) is the one used in the September V5 video. The scorecard behind it, including every player name, is invented. Do not swap in real player names next to made-up figures.

## Traps hit while building

- Export shots are cropped to the viewport height. The viewport must be taller than the post (1920 for a story), which `capture.mjs` sets for each export.
- Tweening `clip-path` strings (with or without `round`) and a CSS variable inside a clip-path did not animate in the Hyperframes render. The size scene uses three separate native-size frames and crossfades them.
- A fill-pass `fromTo` that shares an element with an explicit `set` needs `immediateRender: false`, or the from-values are applied at build time.
- Wrapping text in absolute-positioned blocks fails the layout gate as soon as it wraps. Use a flex row for pills, and size headlines so each line fits.
- Run the render detached (`HYPERFRAMES_RENDER_DETACHED=1`) if the tool kills long commands. It took about 70 seconds here.
