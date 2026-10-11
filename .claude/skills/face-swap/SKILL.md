---
name: face-swap
description: Swap faces in a video or image using a photo, entirely locally with free open-source FaceFusion (no paid service, API key or GPU). Use when the user uploads a photo plus a template video or image and wants their face (or two different people's faces) put onto the people in it, for example dance templates, memes, club promo clips. Handles one or several people per video and keeps the original audio.
---

# Face swap (FaceFusion, free, CPU-capable)

Runs FaceFusion 3.9.1 locally. Everything downloads from github.com, huggingface.co and pypi.org: no account, key or subscription. About 1 GB of Python packages at install, then about 1.5 to 2 GB of models fetched automatically on the first real run (cached after that), so the very first swap in a fresh container takes a minute or two longer.

## Before you start

Only swap faces of people who have agreed to it (the user's own face, or a person who has said yes). Keep results clearly playful or promotional and do not present them as real footage of someone. If the request looks aimed at deceiving people or at someone who has not consented, stop and say why.

## 1. Install (once per container, a few minutes)

The cloud container is wiped between sessions, so check first and install only if missing:

```bash
[ -x ~/tools/ff-venv/bin/python ] || bash .claude/skills/face-swap/scripts/setup.sh
```

Needs `git`, `ffmpeg` and Python 3.10 to 3.12 (or `uv`). Install dir is `$FACE_SWAP_HOME` (default `~/tools`).

## 2. Look at the inputs

Uploads arrive with hashed names under `/root/.claude/uploads/<session>/`. Copy them to the scratchpad with readable names, then:

```bash
ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate,nb_frames,duration -of compact video.mp4
ffmpeg -v error -y -ss 3 -i video.mp4 -frames:v 1 frame.png     # then Read frame.png
```

Read a few frames to count the people, see where they stand, and find a frame where **everyone to be swapped is visible** (that is the `--reference-frame`). Read each source photo too: it should be a clear, roughly front-facing face. If a photo has no detectable face the run fails with a clear message.

## 3. Map photos to people

One `--face POS=photo` per person. POS is the person's place in the reference frame: `left`, `right`, `top`, `bottom`, `large`, `small`, or `POS:N` for the (N+1)th in that order. Use `all=photoA,photoB` to put one identity (blended from the photos) on every face.

If the user gives two photos and the video has two people, ask or infer which photo goes on whom (for example from shirts or the context they described). Do not guess silently: state the mapping you used.

## 4. Preview, then render

Always preview a short slice first (about 24 frames) and check the crops before the full run:

```bash
python3 -I .claude/skills/face-swap/scripts/face_swap.py video.mp4 -o preview.mp4 \
  --face left=photoA.jpg --face right=photoB.jpg --trim-end 24
ffmpeg -v error -y -ss 0.5 -i preview.mp4 -frames:v 1 preview.png     # Read it, zoom with a crop if needed
```

Then the full render, in the background because it is slow:

```bash
python3 -I .claude/skills/face-swap/scripts/face_swap.py video.mp4 -o final.mp4 \
  --face left=photoA.jpg --face right=photoB.jpg
```

Use Bash `run_in_background: true` and tell the user the estimate. The wrapper prints one line per pass; the FaceFusion log is in the temp dir it names on failure (add `--keep-work` to keep it).

**Timing on 4 CPU cores, no GPU:** about 2 to 2.5 s per frame per person. A 20 s, 24 fps video (481 frames) is roughly 17 min for one person and 35 min for two. Say this up front. A GPU machine is far faster but is not needed.

## 5. Deliver

Send the result with `SendUserFile`. Mention the mapping, the duration processed and any visible weak spots.

## Options worth knowing

| Flag | Use |
|---|---|
| `--enhance` | GFPGAN face restoration. Sharper faces on soft footage, roughly doubles the time. |
| `--model` | `hyperswap_1a_256` (default, best tested), `hyperswap_1b_256`, `inswapper_128`, `simswap_256`. `inswapper_128` was not faster on CPU. |
| `--reference-frame N` | Frame where all targets are visible, if frame 0 is empty or someone walks in later. |
| `--distance 0.3` | How strictly a face must match the reference identity to be swapped. Raise a little if a person's face is skipped when they turn; lower if the wrong person gets swapped. |
| `--trim-start/--trim-end` | Frame range, for previews. |
| `--quality 90` | Output video quality. Each extra person adds one re-encode, so keep it high. |
| `--ff '--flag value'` | Pass any extra FaceFusion flag straight through (repeatable). Loosening detection (`--face-detector-score 0.2`) did not help on a tiny GIF and made it worse, so preview before trusting it. |

An image target works the same way (`-o out.png`).

**GIFs and small clips.** FaceFusion wants a video, not a GIF, and cannot find faces smaller than about 40 px. For a GIF, upscale to an mp4 first, swap, then convert back:

```bash
ffmpeg -y -i in.gif -vf "scale=iw*4:ih*4:flags=lanczos,format=yuv420p" -r 10 -c:v libx264 -crf 14 up.mp4
python3 -I .claude/skills/face-swap/scripts/face_swap.py up.mp4 -o swapped.mp4 --face large=photo.jpg --reference-frame 10
ffmpeg -y -i swapped.mp4 -vf "fps=10,scale=440:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" -loop 0 out.gif
```

Frames where the head is thrown back or the face is tiny may stay unswapped. To see which frames changed, compare against the input with `ffmpeg -i orig.mp4 -i swapped.mp4 -filter_complex "[0][1]psnr=stats_file=psnr.log" -f null -`: unswapped frames sit a little higher than the rest.

## Known limits

- The swap replaces the face only. Hair, head shape, glasses position and body stay from the template, so a result keeps the template person's silhouette.
- Profile views, heavy blur, hands over the face and fast head turns can flicker or drop the swap on a few frames. Preview a hard moment if the video has one.
- The reference-frame method fails if the people are too similar or too close together to be told apart; swap by position (`left`/`right`) on a frame where they are apart.
- FaceFusion's own code is open source (OpenRAIL-AS). The individual swap models carry their own licences; check them before using output commercially.
