#!/usr/bin/env python3
"""Whole-body character replacement with Wan2.2-Animate, driven headless through ComfyUI.

Give it a template video and a photo of the person who should replace the person in the
video. It keeps the template's scene, camera and motion, and swaps in the photo's person.

Built for a free Colab T4 (15 GB VRAM) using the Q4 GGUF build of the model, but the same
code runs on any CUDA machine. Standard library only, so it imports before ComfyUI exists.

The graph follows QuantStack's published "wan animate native" workflow, with the single
33-frame run replaced by a chain of chunks so a whole clip can be done in one go.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# Tested combination. Bump together and re-validate; ComfyUI moves fast.
PINS = {
    "ComfyUI": ("https://github.com/comfyanonymous/ComfyUI.git", "7f7fd918ed0815c5d5ef2ccfe44bfc8e72cfd217"),
    "ComfyUI-GGUF": ("https://github.com/city96/ComfyUI-GGUF.git", "6ea2651e7df66d7585f6ffee804b20e92fb38b8a"),
    "ComfyUI-KJNodes": ("https://github.com/kijai/ComfyUI-KJNodes.git", "d7641533d6634eb05f8570c980fce8fc8528dc7b"),
    "ComfyUI-VideoHelperSuite": ("https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git", "4d907bee61e92c2e65af3bd6383a4e4d356126d1"),
    "ComfyUI-WanVideoWrapper": ("https://github.com/kijai/ComfyUI-WanVideoWrapper.git", "088128b224242e110d3906c6750e9a3a348a659b"),
    "ComfyUI-segment-anything-2": ("https://github.com/kijai/ComfyUI-segment-anything-2.git", "0c35fff5f382803e2310103357b5e985f5437f32"),
    "comfyui_controlnet_aux": ("https://github.com/Fannovel16/comfyui_controlnet_aux.git", "0cd290477128d42cdc3e76a826a402d866e8c684"),
}

HF = "https://huggingface.co"
# (url, folder under ComfyUI/models, file name ComfyUI will see)
GGUF_QUANTS = ("Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_S", "Q6_K", "Q8_0")
LORA_FILE = "Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
VAE_FILE = "wan_2.1_vae.safetensors"
T5_FP8_FILE = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
T5_GGUF_FILE = "umt5-xxl-encoder-Q5_K_M.gguf"


def model_files(gguf_quant, text_encoder):
    gguf = f"Wan2.2-Animate-14B-{gguf_quant}.gguf"
    files = [
        (f"{HF}/QuantStack/Wan2.2-Animate-14B-GGUF/resolve/main/{gguf}", "unet", gguf),
        (f"{HF}/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/{VAE_FILE}", "vae", VAE_FILE),
        (f"{HF}/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
         "loras", LORA_FILE),
    ]
    if text_encoder == "gguf":
        files.append((f"{HF}/city96/umt5-xxl-encoder-gguf/resolve/main/{T5_GGUF_FILE}", "text_encoders", T5_GGUF_FILE))
    else:
        files.append((f"{HF}/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/{T5_FP8_FILE}",
                      "text_encoders", T5_FP8_FILE))
    return gguf, files


NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，"
    "丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走"
)


@dataclass
class Config:
    comfy_dir: str = "ComfyUI"
    video: str = ""                   # template video
    image: str = ""                   # photo of the replacement person
    out_dir: str = "wan_out"
    prompt: str = "a person dancing"
    width: int = 0                    # 0 = work out from the video (long side = long_side)
    height: int = 0
    long_side: int = 640
    fps: int = 16                     # Wan renders at 16 fps
    max_seconds: float = 10.0
    chunk_len: int = 33               # frames per chunk, must be 4n+1. Lower = less VRAM.
    overlap: int = 5                  # frames carried from one chunk into the next
    steps: int = 6
    seed: int = 42
    # Where the person is in the FIRST frame, as fractions of width/height (x, y).
    # Two or three points on the person (head, torso) segment better than one.
    points: list = field(default_factory=lambda: [(0.5, 0.3), (0.5, 0.65)])
    gguf_quant: str = "Q4_K_S"
    text_encoder: str = "fp8"         # "fp8" (tested workflow) or "gguf" (uses less RAM)
    sage_attention: str = "disabled"  # "auto" only on RTX 30xx/40xx, A100, L4 and newer. T4 must be "disabled".
    sam_device: str = "cuda"          # "cpu" with sam_precision "fp32" if there is no GPU
    sam_precision: str = "fp16"
    host: str = "127.0.0.1"
    port: int = 8188
    preview_frames: int = 24


# --------------------------------------------------------------------------- setup


def sh(cmd, cwd=None, check=True):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], cwd=cwd, check=check)


def install(root, python=None):
    """Clone ComfyUI and the custom nodes at the tested commits and install their requirements."""
    python = python or sys.executable
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in PINS.items():
        dest = root / name if name == "ComfyUI" else root / "ComfyUI" / "custom_nodes" / name
        if not (dest / ".git").exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            sh(["git", "clone", "--quiet", url, dest])
        cur = subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True).stdout.strip()
        if cur != sha:
            sh(["git", "fetch", "--quiet", "origin", sha], cwd=dest, check=False)
            sh(["git", "checkout", "--quiet", sha], cwd=dest)
        req = dest / "requirements.txt"
        if req.exists():
            sh([python, "-m", "pip", "install", "-q", "-r", req])
    return root / "ComfyUI"


def download_models(comfy_dir, gguf_quant="Q4_K_S", text_encoder="fp8"):
    """Download the model files (about 18 GB) into ComfyUI/models. Skips files that are already there."""
    comfy_dir = Path(comfy_dir)
    gguf, files = model_files(gguf_quant, text_encoder)
    for url, folder, name in files:
        dest = comfy_dir / "models" / folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print("have", name)
            continue
        print("downloading", name, flush=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        sh(["curl", "-L", "--fail", "--retry", "5", "--retry-delay", "3", "-C", "-", "-o", tmp, url])
        tmp.rename(dest)
    return gguf


def start_server(cfg, python=None, extra_args=(), log="comfyui.log"):
    """Start ComfyUI in the background on localhost only (nothing is exposed to the internet)."""
    python = python or sys.executable
    comfy = Path(cfg.comfy_dir)
    if server_up(cfg):
        print("ComfyUI already running")
        return None
    logf = open(log, "ab")
    proc = subprocess.Popen(
        [python, "main.py", "--listen", cfg.host, "--port", str(cfg.port), "--disable-auto-launch", *extra_args],
        cwd=comfy, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(120):
        if server_up(cfg):
            print("ComfyUI is up")
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"ComfyUI exited early (code {proc.returncode}); see {log}")
        time.sleep(2)
    raise RuntimeError(f"ComfyUI did not start within 4 minutes; see {log}")


def server_up(cfg):
    try:
        urllib.request.urlopen(f"http://{cfg.host}:{cfg.port}/system_stats", timeout=2).read()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- inputs


def probe(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    return int(s["width"]), int(s["height"]), float(j["format"]["duration"])


def plan(cfg):
    """Work out sizes and frame counts. Returns a dict and fills cfg.width/height."""
    w0, h0, dur = probe(cfg.video)
    if not (cfg.width and cfg.height):
        if w0 >= h0:
            cfg.width = cfg.long_side
            cfg.height = max(16, round(cfg.long_side * h0 / w0 / 16) * 16)
        else:
            cfg.height = cfg.long_side
            cfg.width = max(16, round(cfg.long_side * w0 / h0 / 16) * 16)
    if cfg.width % 16 or cfg.height % 16:
        raise ValueError("width and height must be multiples of 16")
    if (cfg.chunk_len - 1) % 4:
        raise ValueError("chunk_len must be 4n+1 (e.g. 33, 49, 77)")
    n = int(min(dur, cfg.max_seconds) * cfg.fps)
    n = 4 * ((n - 1) // 4) + 1            # VHS 'Wan' format wants 4n+1 frames
    new_per_chunk = cfg.chunk_len - cfg.overlap
    chunks = 1 + max(0, math.ceil((n - cfg.chunk_len) / new_per_chunk))
    return {"frames": n, "chunks": chunks, "seconds": n / cfg.fps, "src_size": (w0, h0), "size": (cfg.width, cfg.height)}


def stage_inputs(cfg):
    """Copy the video and photo into ComfyUI/input and return the names ComfyUI will use."""
    inp = Path(cfg.comfy_dir) / "input"
    inp.mkdir(parents=True, exist_ok=True)
    v = f"src_{Path(cfg.video).stem}{Path(cfg.video).suffix}"
    i = f"ref_{Path(cfg.image).stem}.png"
    shutil.copy(cfg.video, inp / v)
    # normalise the photo to PNG so odd formats / EXIF rotation never reach the graph
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", cfg.image, str(inp / i)], check=True)
    return v, i


def points_preview(cfg, dest="points_preview.png"):
    """Frame 0 at working size with each point drawn as a red square, so the picks can be checked by eye."""
    plan(cfg)
    boxes = ",".join(
        f"drawbox=x={int(x * cfg.width) - 6}:y={int(y * cfg.height) - 6}:w=12:h=12:color=red:t=fill" for x, y in cfg.points)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cfg.video), "-vf",
                    f"scale={cfg.width}:{cfg.height},{boxes}", "-frames:v", "1", str(dest)], check=True)
    return dest


def points_json(cfg):
    pts = [{"x": round(x * cfg.width, 2), "y": round(y * cfg.height, 2)} for x, y in cfg.points]
    return json.dumps(pts)


# --------------------------------------------------------------------------- the graph


class Graph:
    def __init__(self):
        self.nodes = {}
        self._n = 0

    def add(self, class_type, **inputs):
        self._n += 1
        nid = str(self._n)
        self.nodes[nid] = {"class_type": class_type, "inputs": inputs}
        return nid

    @staticmethod
    def out(nid, slot=0):
        return [nid, slot]


def _front_half(g, cfg, video_name, n_frames):
    """Load the video and build the pose, face, mask and background videos (shared by preview and full)."""
    W, H = cfg.width, cfg.height
    load = g.add("VHS_LoadVideo", video=video_name, force_rate=cfg.fps, custom_width=W, custom_height=H,
                 frame_load_cap=n_frames, skip_first_frames=0, select_every_nth=1, format="Wan")
    frames = g.add("ImageResizeKJv2", image=g.out(load), width=W, height=H, upscale_method="nearest-exact",
                   keep_proportion="stretch", pad_color="0, 0, 0", crop_position="center", divisible_by=2, device="cpu")
    ppr = g.add("PixelPerfectResolution", original_image=g.out(frames), image_gen_width=W, image_gen_height=H,
                resize_mode="Just Resize")
    # detect_face must be "enable": FaceMaskFromPoseKeypoints needs the face points, and with it off the
    # face crop silently becomes an empty patch of background (verified on a real clip).
    dw = g.add("DWPreprocessor", image=g.out(frames), detect_hand="disable", detect_body="enable", detect_face="enable",
               resolution=g.out(ppr), bbox_detector="yolox_l.torchscript.pt",
               pose_estimator="dw-ll_ucoco_384_bs5.torchscript.pt", scale_stick_for_xinsr_cn="disable")
    pose = g.add("ImageResizeKJv2", image=g.out(dw, 0), width=W, height=H, upscale_method="nearest-exact",
                 keep_proportion="stretch", pad_color="0, 0, 0", crop_position="center", divisible_by=2, device="cpu")
    face_mask = g.add("FaceMaskFromPoseKeypoints", pose_kps=g.out(dw, 1), person_index=0)
    face = g.add("ImageCropByMaskAndResize", image=g.out(frames), mask=g.out(face_mask), base_resolution=512,
                 padding=0, min_crop_resolution=128, max_crop_resolution=512)
    sam = g.add("DownloadAndLoadSAM2Model", model="sam2_hiera_base_plus.safetensors", segmentor="video",
                device=cfg.sam_device, precision=cfg.sam_precision)
    seg = g.add("Sam2Segmentation", sam2_model=g.out(sam), image=g.out(frames), keep_model_loaded=False,
                coordinates_positive=points_json(cfg), individual_objects=False)
    grow = g.add("GrowMask", mask=g.out(seg), expand=20, tapered_corners=True)
    block = g.add("BlockifyMask", masks=g.out(grow), block_size=32)
    bg = g.add("DrawMaskOnImage", image=g.out(frames), mask=g.out(block), color="0, 0, 0")
    return {"frames": frames, "pose": pose, "face": face, "mask": block, "bg": bg}


def _save(g, images, cfg, prefix, n_frames=None):
    if n_frames:
        images = g.out(g.add("ImageFromBatch", image=images, batch_index=0, length=n_frames))
    return g.add("VHS_VideoCombine", images=images, frame_rate=cfg.fps, loop_count=0, filename_prefix=prefix,
                 format="video/h264-mp4", pix_fmt="yuv420p", crf=19, save_metadata=False, trim_to_audio=False,
                 pingpong=False, save_output=True)


def build_preview(cfg, video_name, n_frames):
    """Cheap graph: mask overlay, pose and face crop for the first frames. No big model is loaded."""
    g = Graph()
    f = _front_half(g, cfg, video_name, n_frames)
    for key, prefix in (("bg", "preview_mask"), ("pose", "preview_pose"), ("face", "preview_face")):
        _save(g, g.out(f[key]) if isinstance(f[key], str) else f[key], cfg, prefix)
    return g.nodes


def build_full(cfg, video_name, image_name, n_frames, n_chunks, dry_run=False):
    """The whole job as one ComfyUI graph.

    dry_run=True skips the text encoder, the 14B model and the sampler (uses a fixed dummy conditioning and
    decodes the empty latent). It exercises the real chunking, trimming and stitching arithmetic with only the
    small VAE, so the frame bookkeeping can be checked on a CPU. The result is grey video, not a real swap.
    """
    g = Graph()
    W, H, L = cfg.width, cfg.height, cfg.chunk_len

    # models
    vae = g.add("VAELoader", vae_name=VAE_FILE)
    if dry_run:
        model = None
        pos = neg = g.add("LotusConditioning")
    else:
        if cfg.text_encoder == "gguf":
            clip = g.add("CLIPLoaderGGUF", clip_name=T5_GGUF_FILE, type="wan")
        else:
            clip = g.add("CLIPLoader", clip_name=T5_FP8_FILE, type="wan", device="default")
        unet = g.add("UnetLoaderGGUF", unet_name=f"Wan2.2-Animate-14B-{cfg.gguf_quant}.gguf")
        sage = g.add("PathchSageAttentionKJ", model=g.out(unet), sage_attention=cfg.sage_attention)
        lora = g.add("LoraLoaderModelOnly", model=g.out(sage), lora_name=LORA_FILE, strength_model=1.0)
        model = g.add("ModelSamplingSD3", model=g.out(lora), shift=8.0)
        pos = g.add("CLIPTextEncode", text=cfg.prompt, clip=g.out(clip))
        neg = g.add("CLIPTextEncode", text=NEGATIVE, clip=g.out(clip))

    # the replacement person
    img = g.add("LoadImage", image=image_name)
    ref = g.add("ImageResizeKJv2", image=g.out(img, 0), width=W, height=H, upscale_method="lanczos",
                keep_proportion="pad_edge_pixel", pad_color="0, 0, 0", crop_position="center", divisible_by=16, device="cpu")

    f = _front_half(g, cfg, video_name, n_frames)

    prev_images = None
    prev_offset = None
    chunk_outputs = []
    for k in range(n_chunks):
        kw = dict(positive=g.out(pos), negative=g.out(neg), vae=g.out(vae), width=W, height=H, length=L, batch_size=1,
                  reference_image=g.out(ref), face_video=g.out(f["face"]), pose_video=g.out(f["pose"]),
                  continue_motion_max_frames=cfg.overlap, background_video=g.out(f["bg"]),
                  character_mask=g.out(f["mask"]), video_frame_offset=0)
        if k > 0:
            kw["continue_motion"] = prev_images
            kw["video_frame_offset"] = prev_offset
        a = g.add("WanAnimateToVideo", **kw)
        if dry_run:
            latent = g.out(a, 2)
        else:
            latent = g.out(g.add("KSampler", model=g.out(model), seed=cfg.seed, steps=cfg.steps, cfg=1.0,
                                 sampler_name="euler", scheduler="simple", positive=g.out(a, 0),
                                 negative=g.out(a, 1), latent_image=g.out(a, 2), denoise=1.0))
        trim = g.add("TrimVideoLatent", samples=latent, trim_amount=g.out(a, 3))
        dec = g.add("VAEDecode", samples=g.out(trim), vae=g.out(vae))
        if k == 0:
            imgs = g.out(dec)
        else:
            # drop the frames that only re-state the previous chunk's ending
            imgs = g.out(g.add("ImageFromBatch", image=g.out(dec), batch_index=g.out(a, 4), length=4096))
        chunk_outputs.append(imgs)
        prev_images = imgs
        prev_offset = g.out(a, 5)

    joined = chunk_outputs[0]
    for nxt in chunk_outputs[1:]:
        joined = g.out(g.add("ImageBatch", image1=joined, image2=nxt))
    _save(g, joined, cfg, "wan_replace", n_frames=n_frames)
    return g.nodes


# --------------------------------------------------------------------------- running


def _post(cfg, prompt):
    body = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode()
    req = urllib.request.Request(f"http://{cfg.host}:{cfg.port}/prompt", data=body, headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}")
        errs = []
        for nid, ne in (detail.get("node_errors") or {}).items():
            for er in ne.get("errors", []):
                errs.append(f"node {nid} ({ne.get('class_type')}): {er.get('message')} {er.get('details')}")
        raise RuntimeError("ComfyUI rejected the graph:\n  " + "\n  ".join(errs or [json.dumps(detail)[:800]])) from None


def _history(cfg, pid):
    try:
        return json.loads(urllib.request.urlopen(f"http://{cfg.host}:{cfg.port}/history/{pid}", timeout=30).read()).get(pid)
    except Exception:
        return None


def log_progress(log="comfyui.log"):
    """Last progress line from the ComfyUI log (the sampler's it/s bar), for status messages."""
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 6000))
            text = f.read().decode(errors="replace")
    except OSError:
        return ""
    bars = [p.strip() for p in re.split(r"[\r\n]", text) if "%|" in p]
    return bars[-1][:140] if bars else ""


def wait(cfg, pid, timeout=6 * 3600, every=15, log="comfyui.log"):
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        h = _history(cfg, pid)
        if h:
            st = h.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                detail = msgs[-1][1] if msgs else st
                raise RuntimeError(
                    f"ComfyUI failed in node {detail.get('node_id')} ({detail.get('node_type')}): "
                    f"{detail.get('exception_message', '')[:600]}")
            if st.get("completed"):
                return h["outputs"]
        msg = f"[{int(time.time() - t0)}s] {log_progress(log)}"
        if msg != last:
            print(msg, flush=True)
            last = msg
        time.sleep(every)
    raise TimeoutError("job did not finish in time")


def _collect(cfg, outputs):
    files = []
    base = Path(cfg.comfy_dir) / "output"
    for o in outputs.values():
        for item in o.get("gifs", []) + o.get("videos", []) + o.get("images", []):
            files.append(base / item.get("subfolder", "") / item["filename"])
    return files


def run_preview(cfg, every=3):
    """Mask overlay, pose and face crop for the first few frames. Check these before the long run."""
    info = plan(cfg)
    v, _ = stage_inputs(cfg)
    n = 4 * ((min(cfg.preview_frames, info["frames"]) - 1) // 4) + 1
    pid = _post(cfg, build_preview(cfg, v, n))
    files = _collect(cfg, wait(cfg, pid, every=every))
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    for f in files:
        if f.suffix == ".mp4":
            dest = out / re.sub(r"_\d+_?\.mp4$", ".mp4", f.name)
            shutil.copy(f, dest)
            result[dest.stem] = dest
    return result


def run_full(cfg):
    info = plan(cfg)
    v, i = stage_inputs(cfg)
    print(f"{info['frames']} frames ({info['seconds']:.1f}s) at {cfg.width}x{cfg.height}, {info['chunks']} chunk(s) of {cfg.chunk_len}")
    pid = _post(cfg, build_full(cfg, v, i, info["frames"], info["chunks"]))
    files = [f for f in _collect(cfg, wait(cfg, pid)) if f.suffix == ".mp4"]
    if not files:
        raise RuntimeError("the job finished but produced no video")
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "replaced_raw.mp4"
    shutil.copy(files[0], dest)
    return dest


def finalize(raw, source_video, dest, scale_to_source=True, smooth_to_source_fps=False, cfg=None):
    """Put the template's audio back and optionally scale / smooth the 16 fps result."""
    w0, h0, _ = probe(source_video)
    rate = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                           "-of", "csv=p=0", str(source_video)], capture_output=True, text=True).stdout.strip()
    num, den = (rate.split("/") + ["1"])[:2]
    src_fps = float(num) / float(den or 1)
    vf = []
    if smooth_to_source_fps:
        vf.append(f"minterpolate=fps={src_fps:.3f}:mi_mode=mci:mc_mode=aobmc:vsbmc=1")
    if scale_to_source:
        vf.append(f"scale={w0 - w0 % 2}:{h0 - h0 % 2}:flags=lanczos")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(raw)],
                               capture_output=True, text=True).stdout.strip())
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-i", str(source_video), "-map", "0:v:0", "-map", "1:a:0?"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", f"{dur:.3f}", str(dest)]
    subprocess.run(cmd, check=True)
    return Path(dest)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["install", "models", "preview", "run"])
    ap.add_argument("--root", default="wan_root")
    ap.add_argument("--video")
    ap.add_argument("--image")
    ap.add_argument("--out", default="wan_out")
    ap.add_argument("--points", default="0.5,0.3;0.5,0.65", help="x,y fractions of the first frame, ';'-separated")
    ap.add_argument("--max-seconds", type=float, default=10.0)
    ap.add_argument("--quant", default="Q4_K_S", choices=GGUF_QUANTS)
    ap.add_argument("--text-encoder", default="fp8", choices=["fp8", "gguf"])
    ap.add_argument("--sage", default="disabled")
    a = ap.parse_args()
    comfy = str(Path(a.root) / "ComfyUI")
    if a.step == "install":
        install(a.root)
    elif a.step == "models":
        download_models(comfy, a.quant, a.text_encoder)
    else:
        c = Config(comfy_dir=comfy, video=a.video, image=a.image, out_dir=a.out, max_seconds=a.max_seconds,
                   gguf_quant=a.quant, text_encoder=a.text_encoder, sage_attention=a.sage,
                   points=[tuple(map(float, p.split(","))) for p in a.points.split(";")])
        start_server(c)
        print(run_preview(c) if a.step == "preview" else run_full(c))
