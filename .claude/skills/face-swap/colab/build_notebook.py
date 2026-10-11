#!/usr/bin/env python3
"""Builds wan_animate_colab.ipynb with wan_replace.py embedded, so the notebook is self-contained.

    python3 build_notebook.py        # rewrites wan_animate_colab.ipynb next to this file
"""
import json
from pathlib import Path

here = Path(__file__).parent
helper = (here / "wan_replace.py").read_text()


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


cells = [
    md("""
# Swap a whole person into a video (free Colab)

Upload a template video and a photo. The notebook replaces the person in the video with the person in the
photo, including hair, body and clothes, and keeps the video's motion, camera and background. It runs
Wan2.2-Animate (14B, 4-bit GGUF build) through ComfyUI on Colab's free T4 GPU. No account, key or paid plan is needed.

**Read this first: Colab's rules.** Google's Colab FAQ lists "creating deepfakes" as disallowed on all managed
runtimes. This notebook puts a real person's likeness into a video of someone else, and Google decides what counts.
If it does, Colab can end the runtime without warning and may restrict the account. You run it at your own risk. The
same code (`wan_replace.py`) works on any machine with an NVIDIA GPU, including your own or a rented one (a rental provider has
its own terms, so check them). The notebook itself does not open a web UI, which is a separate free-tier rule.

**Before you start**

1. Runtime > Change runtime type > **T4 GPU**.
2. Use photos of people who have agreed to it (yourself, or someone who said yes), and don't pass the result off as real footage.
3. The photo works best as a clear, front-facing shot of the whole person, or at least head to hips, with nothing held across the body.

**What to expect**

* First-time setup downloads about 19 GB and takes roughly 15 to 25 minutes.
* The settings below start with a **2 second test**. Time that run, then decide how much of the clip to do.
  Longer clips are processed in chunks of about 2 seconds each, so the cost grows in a straight line.
* Free Colab can disconnect and has daily GPU limits. Download your result as soon as it finishes.
"""),
    md("## 1. Check the GPU"),
    code('''
import subprocess
gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                     capture_output=True, text=True).stdout.strip()
print(gpu or "No GPU found. Use Runtime > Change runtime type > T4 GPU, then run this cell again.")
'''),
    md("## 2. Upload the video and the photo\nSelect both files in the same dialog. A GIF is fine; it is converted to a video."),
    code('''
import os, subprocess
from google.colab import files

os.makedirs("inputs", exist_ok=True)
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".gif")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")
VIDEO = IMAGE = None
for name in files.upload():
    dest = os.path.join("inputs", name)
    os.replace(name, dest)
    low = name.lower()
    if low.endswith(VIDEO_EXT):
        VIDEO = dest
    elif low.endswith(IMAGE_EXT):
        IMAGE = dest
if VIDEO and VIDEO.lower().endswith(".gif"):
    mp4 = VIDEO.rsplit(".", 1)[0] + ".mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", VIDEO, "-vf",
                    "scale='max(iw,640)':-2:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "14", mp4], check=True)
    VIDEO = mp4
assert VIDEO and IMAGE, "Upload one video (or GIF) and one photo."
print("video:", VIDEO, "\\nphoto:", IMAGE)
'''),
    md("""
## 3. Settings

`POINTS` says where the person is in the **first frame**, as fractions of the width and height
(x, y), where (0, 0) is the top left and (1, 1) is the bottom right. Put one point on the head and one on the torso.
The next cell draws them on the frame so you can check.
"""),
    code('''
MAX_SECONDS = 2.1       #@param {type:"number"}
LONG_SIDE = 640         #@param [512, 640, 768, 832] {type:"raw"}
PROMPT = "a person dancing"  #@param {type:"string"}
POINTS = [(0.5, 0.30), (0.5, 0.65)]   # head, torso
GGUF_QUANT = "Q4_K_S"   #@param ["Q3_K_M", "Q4_K_S", "Q4_K_M"]
TEXT_ENCODER = "fp8"    #@param ["fp8", "gguf"]
SEED = 42               #@param {type:"integer"}
'''),
    md("## 4. Write the helper code\nThis cell contains the whole pipeline. Nothing here needs editing."),
    code("%%writefile wan_replace.py\n" + helper),
    md("## 5. Install ComfyUI and download the models (slow, once per session)"),
    code('''
import sys
sys.path.insert(0, ".")
import wan_replace as w

ROOT = "/content/wan"
w.install(ROOT)
w.download_models(f"{ROOT}/ComfyUI", GGUF_QUANT, TEXT_ENCODER)
'''),
    md("## 6. Start the engine and check where the person is"),
    code('''
from IPython.display import Image, Video, display

cfg = w.Config(comfy_dir=f"{ROOT}/ComfyUI", video=VIDEO, image=IMAGE, out_dir="wan_out", prompt=PROMPT,
               long_side=LONG_SIDE, max_seconds=MAX_SECONDS, points=POINTS, gguf_quant=GGUF_QUANT,
               text_encoder=TEXT_ENCODER, seed=SEED)
print(w.plan(cfg))
w.start_server(cfg)
display(Image(w.points_preview(cfg)))
'''),
    md("""
The red squares should sit on the person. If they don't, edit `POINTS` in step 3 and run steps 3 and 6 again.

### Preview the masks (cheap, no big model)
This shows what the model will be told: the person blocked out of the background, the pose skeleton, and the
face crop. Fix any problem here before the long run.
"""),
    code('''
preview = w.run_preview(cfg)
for name in ("preview_mask", "preview_pose", "preview_face"):
    print(name)
    display(Video(str(preview[name]), embed=True, width=420))
'''),
    md("""
Check three things:

* **preview_mask**: the black shape should cover the whole person and not much else.
* **preview_pose**: a stick figure that follows the dancer.
* **preview_face**: a crop of the head that follows the face. If it shows background, the person was not found; adjust `POINTS`.
"""),
    md("## 7. Make the video\nThe 2 second test comes first. Note how long it takes (see the timer in the output)."),
    code('''
import time
t0 = time.time()
raw = w.run_full(cfg)
print(f"done in {(time.time() - t0) / 60:.1f} minutes -> {raw}")
display(Video(str(raw), embed=True, width=480))
'''),
    md("""
If it looks right, raise `MAX_SECONDS` in step 3, run steps 3 and 6, then run step 7 again. Setup (step 5) does not need to be repeated.

## 8. Add the audio back and download
Wan renders at 16 frames per second. `SMOOTH` interpolates up to the original frame rate (slower, can leave soft edges).
"""),
    code('''
SCALE_TO_SOURCE = True   #@param {type:"boolean"}
SMOOTH = False           #@param {type:"boolean"}
final = w.finalize(raw, VIDEO, "wan_out/final.mp4", scale_to_source=SCALE_TO_SOURCE, smooth_to_source_fps=SMOOTH)
display(Video(str(final), embed=True, width=480))
from google.colab import files
files.download(str(final))
'''),
    md("""
## If something goes wrong

| What you see | What to try |
|---|---|
| Out of memory (VRAM) during the sampler | Step 3: `LONG_SIDE = 512`, and `GGUF_QUANT = "Q3_K_M"`. Then run steps 3, 5, 6 and 7 again. |
| Out of memory (RAM) while loading | Step 3: `TEXT_ENCODER = "gguf"`. Then run steps 3, 5, 6 and 7 again. |
| The person is not replaced, or only partly | Check the red squares and the `preview_mask` video. Move `POINTS` onto the person. |
| The face looks different from the photo | Use a sharper, front-facing photo with no glasses glare or objects across the body. |
| The look shifts every couple of seconds | Chunk joins. Keep clips short, or try a different `SEED`. |
| Session disconnected | Runtime > Run all again. Downloaded models do not survive a disconnect. |
| `ComfyUI failed in node ...` | Copy the message. It names the node that failed. |
"""),
]

nb = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"gpuType": "T4", "provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
out = here / "wan_animate_colab.ipynb"
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
print("wrote", out, f"({len(cells)} cells)")
