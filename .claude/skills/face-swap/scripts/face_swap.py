#!/usr/bin/env python3
"""Swap faces in a video or image with FaceFusion (local, free, CPU-capable).

Each --face assignment runs one FaceFusion pass, chained, so different people in the
target can get different source photos.

  face_swap.py template.mp4 -o out.mp4 --face left=a.jpg --face right=b.jpg
  face_swap.py clip.mp4     -o out.mp4 --face all=a.jpg,b.jpg      # blend photos, swap every face

POS is one of left, right, top, bottom, large, small (optionally POS:N for the
(N+1)th face in that order, e.g. left:1 is second from the left) or "all".
The face is chosen on a reference frame (--reference-frame) and then followed through the
video by identity, so people can move around without the mapping flipping.

Standard library only. Run with the system python3.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path(os.environ.get("FACE_SWAP_HOME", Path.home() / "tools"))
REPO = HOME / "facefusion"
PY = HOME / "ff-venv" / "bin" / "python"

ORDERS = {
    "left": "left-right", "right": "right-left",
    "top": "top-bottom", "bottom": "bottom-top",
    "large": "large-small", "small": "small-large",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def parse_face(spec):
    if "=" not in spec:
        sys.exit(f"--face expects POS=photo[,photo]; got {spec!r}")
    pos, photos = spec.split("=", 1)
    photos = [str(Path(p).expanduser().resolve()) for p in photos.split(",") if p]
    for p in photos:
        if not Path(p).is_file():
            sys.exit(f"source photo not found: {p}")
    if not photos:
        sys.exit(f"--face {spec!r} has no photos")
    m = re.fullmatch(r"(left|right|top|bottom|large|small)(?::(\d+))?", pos)
    if pos == "all":
        return {"pos": "all", "photos": photos}
    if not m:
        sys.exit(f"unknown position {pos!r}; use left, right, top, bottom, large, small or all")
    return {"pos": m.group(1), "index": int(m.group(2) or 0), "photos": photos}


def build_cmd(a, face, src_target, dst):
    cmd = [str(PY), "facefusion.py", "headless-run",
           "-s", *face["photos"], "-t", str(src_target), "-o", str(dst),
           "--processors", "face_swapper",
           "--face-swapper-model", a.model,
           "--execution-providers", a.providers,
           "--execution-thread-count", str(a.threads),
           "--temp-path", str(a.work / "ff-temp"), "--jobs-path", str(a.work / "ff-jobs"),
           "--output-video-quality", str(a.quality),
           "--log-level", "info"]
    if a.enhance:
        cmd[cmd.index("face_swapper") + 1:cmd.index("face_swapper") + 1] = ["face_enhancer"]
        cmd += ["--face-enhancer-model", "gfpgan_1.4", "--face-enhancer-blend", str(a.enhance_blend)]
    if face["pos"] == "all":
        cmd += ["--face-selector-mode", "many"]
    else:
        cmd += ["--face-selector-mode", "reference",
                "--face-selector-order", ORDERS[face["pos"]],
                "--reference-face-position", str(face["index"]),
                "--reference-frame-number", str(a.reference_frame),
                "--reference-face-distance", str(a.distance)]
    if a.trim_start is not None:
        cmd += ["--trim-frame-start", str(a.trim_start)]
    if a.trim_end is not None:
        cmd += ["--trim-frame-end", str(a.trim_end)]
    return cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="video or image that contains the faces to replace")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--face", action="append", required=True, metavar="POS=photo[,photo]")
    ap.add_argument("--model", default="hyperswap_1a_256",
                    help="face swapper model (hyperswap_1a_256, hyperswap_1b_256, inswapper_128, simswap_256 ...)")
    ap.add_argument("--enhance", action="store_true", help="also run GFPGAN face enhancer (sharper, much slower on CPU)")
    ap.add_argument("--enhance-blend", type=int, default=80)
    ap.add_argument("--reference-frame", type=int, default=0,
                    help="frame number where every person to swap is visible (default 0)")
    ap.add_argument("--distance", type=float, default=0.3,
                    help="identity match tolerance when following a face (0-1, higher = looser)")
    ap.add_argument("--trim-start", type=int, help="first frame to process (for quick previews)")
    ap.add_argument("--trim-end", type=int, help="end frame, exclusive")
    ap.add_argument("--quality", type=int, default=90, help="output video quality 0-100")
    ap.add_argument("--providers", default="cpu")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--keep-work", action="store_true")
    a = ap.parse_args()

    if not PY.exists() or not REPO.exists():
        sys.exit(f"FaceFusion not installed in {HOME}. Run scripts/setup.sh first.")
    target = Path(a.target).expanduser().resolve()
    if not target.is_file():
        sys.exit(f"target not found: {target}")
    out = Path(a.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    is_image = target.suffix.lower() in IMAGE_EXT
    faces = [parse_face(f) for f in a.face]
    if any(f["pos"] == "all" for f in faces) and len(faces) > 1:
        sys.exit('"all" swaps every face, so it cannot be combined with other --face assignments')

    a.work = Path(tempfile.mkdtemp(prefix="face-swap-"))
    log = a.work / "facefusion.log"
    current = target
    t0 = time.time()
    for i, face in enumerate(faces, 1):
        last = i == len(faces)
        dst = out if last else a.work / f"pass{i}{target.suffix}"
        cmd = build_cmd(a, face, current, dst)
        label = face["pos"] + (f":{face['index']}" if face.get("index") else "")
        print(f"[{i}/{len(faces)}] {label} <- {', '.join(Path(p).name for p in face['photos'])}", flush=True)
        with open(log, "ab") as lf:
            lf.write(f"\n=== pass {i}: {' '.join(cmd)}\n".encode())
            rc = subprocess.run(cmd, cwd=REPO, stdout=lf, stderr=subprocess.STDOUT).returncode
        if rc != 0 or not dst.exists():
            text = log.read_bytes().decode(errors="replace").replace("\r", "\n")
            tail = [l for l in text.splitlines() if l.strip() and not l.startswith("downloading")][-15:]
            print("\n".join(tail), file=sys.stderr)
            sys.exit(f"pass {i} failed (full log: {log}). Common cause: no face found in a source photo "
                     "or in the reference frame; try a clearer front-facing photo or --reference-frame.")
        current = dst
    print(f"done in {time.time() - t0:.0f}s -> {out}")
    if not a.keep_work:
        shutil.rmtree(a.work, ignore_errors=True)
    else:
        print(f"work dir kept: {a.work}")


if __name__ == "__main__":
    main()
