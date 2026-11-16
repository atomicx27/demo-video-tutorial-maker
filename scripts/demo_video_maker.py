#!/usr/bin/env python3
"""
Demo Video & Tutorial Maker CLI
Turns browser walkthrough screenshots + HUD logs + JSON storyboards into
narrated MP4/WebP/GIF demo videos with voiceover TTS, chapter cards,
spotlight focus boxes, cursor ripples, auto-placed callouts, SRT/VTT captions,
and Markdown tutorial guides.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

WIDTH = 1280
VIEWPORT_H = 848
FOOTER_H = 112
TOTAL_H = VIEWPORT_H + FOOTER_H  # 960 (divisible by 16 for H.264)
FPS = 12
SAMPLE_RATE = 24000

DEFAULT_THEME = {
    "brand_name": "Product Walkthrough",
    "logo_text": "demo",
    "accent_color": "#FF7900",
    "dark_bg": "#000000",
    "card_bg": "#141414",
    "text_color": "#FFFFFF",
    "badge_text_color": "#000000",
}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a #RRGGBB hex string to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 121, 0)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load a crisp cross-platform UI font with fallback."""
    candidates = (
        [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


FONTS = {
    "kicker": load_font(16, bold=True),
    "chap_title": load_font(44, bold=True),
    "chap_bullet": load_font(23, bold=False),
    "badge": load_font(16, bold=True),
    "phase": load_font(15, bold=True),
    "headline": load_font(22, bold=True),
    "subtitle": load_font(18, bold=False),
    "callout_title": load_font(16, bold=True),
    "callout_body": load_font(15, bold=False),
    "counter": load_font(15, bold=True),
    "logo": load_font(16, bold=True),
}


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_spacing: int = 5,
) -> int:
    """Wrap and draw text within max_width, returning the next Y position."""
    words = text.split()
    lines = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    x, y = xy
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        bb = draw.textbbox((0, 0), line, font=font)
        y += (bb[3] - bb[1]) + line_spacing
    return y


def parse_hud_metadata(hud_path: Path) -> dict:
    """Extract URL, Title, Heading, and Alert from a browser_sandbox HUD text file."""
    meta = {"url": "", "title": "", "heading": "", "alert": ""}
    if not hud_path.exists():
        return meta
    content = hud_path.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("URL:") and not meta["url"]:
            meta["url"] = s[4:].strip()
        elif s.startswith("Title:") and not meta["title"]:
            meta["title"] = s[6:].strip()
        elif "heading " in s and not meta["heading"]:
            m = re.search(r'heading\s+"([^"]+)"', s)
            if m:
                meta["heading"] = m.group(1)
        elif s.startswith("- alert:") and not meta["alert"]:
            meta["alert"] = s[8:].strip()
    return meta


def cmd_init_manifest(args: argparse.Namespace) -> int:
    """Scan a browser_sandbox directory and generate a starter scenes manifest JSON."""
    sandbox = Path(args.sandbox_dir)
    screenshots_dir = sandbox / "screenshots"
    outputs_dir = sandbox / "outputs"
    if not screenshots_dir.is_dir():
        print(f"Error: screenshots directory not found at {screenshots_dir}", file=sys.stderr)
        return 1

    pngs = sorted(
        screenshots_dir.glob("step_*.png"),
        key=lambda p: int(re.search(r"step_(\d+)", p.stem).group(1))
        if re.search(r"step_(\d+)", p.stem)
        else 0,
    )
    if not pngs:
        print(f"Error: no step_*.png files found in {screenshots_dir}", file=sys.stderr)
        return 1

    scenes = [
        {
            "type": "chapter",
            "kicker": "PRODUCT DEMO & WALKTHROUGH",
            "title": args.title,
            "bullets": [
                "Live browser end-to-end walkthrough",
                "Visual callouts and step-by-step narration",
                "Verification and workflow summary",
            ],
            "narration": f"Welcome to the {args.title} walkthrough. Let us step through the live application workflow.",
        }
    ]

    for idx, png in enumerate(pngs, start=1):
        m = re.search(r"step_(\d+)", png.stem)
        step_num = m.group(1) if m else str(idx)
        hud = parse_hud_metadata(outputs_dir / f"step_{step_num}_hud.txt")
        headline = hud["heading"] or hud["title"] or f"Workflow Step {idx:02d}"
        callout_body = hud["alert"] or (f"Active URL: {hud['url']}" if hud["url"] else "Live browser capture.")
        scenes.append(
            {
                "type": "step",
                "file": png.name,
                "step_label": f"STEP {idx:02d}",
                "phase": "WALKTHROUGH",
                "headline": headline[:60],
                "callout_pos": "auto",
                "callout_title": "Key Action",
                "callout_body": callout_body[:140],
                "narration": f"Step {idx}: {headline}. {hud['alert']}".strip(),
                "focus_box": None,
                "cursor_xy": None,
                "zoom_focus": False,
                "export_name": f"tutorial_step_{idx:02d}.png" if idx <= 12 else None,
            }
        )

    manifest = {
        "title": args.title,
        "screenshots_dir": str(screenshots_dir),
        "theme": {
            **DEFAULT_THEME,
            "brand_name": args.brand_name,
            "accent_color": args.accent_color,
        },
        "tts": {
            "engine": "edge-tts",
            "voice": args.voice,
            "rate": "+6%",
        },
        "video": {
            "mp4_name": "demo_tutorial_recording.mp4",
            "webp_name": "demo_tutorial_recording.webp",
            "gif_name": "demo_tutorial_recording.gif",
            "guide_name": "TUTORIAL.md",
            "fps": FPS,
        },
        "scenes": scenes,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifest generated with {len(pngs)} steps -> {out_path}")
    return 0


async def _synthesize_edge_tts(text: str, voice: str, rate: str, mp3_path: Path) -> None:
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(str(mp3_path))


def _synthesize_sapi_wav(text: str, raw_wav: Path) -> None:
    safe_txt = text.replace("'", "''")
    ps_code = "\n".join(
        [
            "Add-Type -AssemblyName System.Speech",
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
            "$s.Rate = 1",
            "try { $s.SelectVoice('Microsoft Zira Desktop') } catch {}",
            f"$s.SetOutputToWaveFile('{raw_wav}')",
            f"$s.Speak('{safe_txt}')",
            "$s.Dispose()",
        ]
    )
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_code], check=True)


def get_cached_tts_wav(text: str, tts_cfg: dict, cache_dir: Path) -> Path:
    """Synthesize or reuse a SHA-256 cached 24kHz mono 16-bit PCM WAV clip."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    voice = tts_cfg.get("voice", "en-US-AriaNeural")
    rate = tts_cfg.get("rate", "+6%")
    engine = tts_cfg.get("engine", "edge-tts")

    digest = hashlib.sha256(f"{engine}|{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:24]
    wav_path = cache_dir / f"{digest}.wav"
    if wav_path.exists() and wav_path.stat().st_size > 44:
        return wav_path

    tmp_src = cache_dir / f"{digest}.tmp_audio"
    try:
        if engine == "edge-tts":
            mp3_path = cache_dir / f"{digest}.mp3"
            asyncio.run(_synthesize_edge_tts(text, voice, rate, mp3_path))
            tmp_src = mp3_path
        else:
            raise RuntimeError("Using SAPI fallback")
    except Exception:
        raw_wav = cache_dir / f"{digest}_sapi.wav"
        _synthesize_sapi_wav(text, raw_wav)
        tmp_src = raw_wav

    subprocess.run(
        [
            FFMPEG_EXE,
            "-y",
            "-i",
            str(tmp_src),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if tmp_src.exists():
        tmp_src.unlink()
    return wav_path


def read_wav_pcm(wav_path: Path) -> np.ndarray:
    """Read normalized 24kHz mono 16-bit PCM samples."""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    return np.frombuffer(frames, dtype=np.int16)


def choose_callout_corner(scene: dict, card_w: int, card_h: int) -> tuple[int, int]:
    """Select corner coordinates (x, y) avoiding focus_box and cursor_xy when set to 'auto'."""
    pos = scene.get("callout_pos", "auto")
    margin_x = 28
    top_y = 92
    bot_y = VIEWPORT_H - card_h - 22
    corners = {
        "tr": (WIDTH - card_w - margin_x, top_y),
        "br": (WIDTH - card_w - margin_x, bot_y),
        "tl": (margin_x, top_y),
        "bl": (margin_x, bot_y),
    }
    if pos in corners:
        return corners[pos]

    target = None
    if scene.get("focus_box"):
        x1, y1, x2, y2 = scene["focus_box"]
        target = ((x1 + x2) / 2, (y1 + y2) / 2)
    elif scene.get("cursor_xy"):
        target = tuple(scene["cursor_xy"])

    if not target:
        return corners["br"]

    tx, ty = target
    best_corner = max(
        corners.values(),
        key=lambda c: ((c[0] + card_w / 2 - tx) ** 2 + (c[1] + card_h / 2 - ty) ** 2),
    )
    return best_corner


def apply_focus_and_cursor(img: Image.Image, scene: dict, accent: tuple[int, int, int]) -> Image.Image:
    """Apply optional spotlight dimming around focus_box and draw cursor ripple."""
    out = img.convert("RGBA")
    focus_box = scene.get("focus_box")
    cursor_xy = scene.get("cursor_xy")

    if focus_box:
        x1, y1, x2, y2 = [int(v) for v in focus_box]
        overlay = Image.new("RGBA", out.size, (0, 0, 0, 95))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 0))
        out = Image.alpha_composite(out, overlay)
        draw = ImageDraw.Draw(out)
        draw.rectangle([x1 - 2, y1 - 2, x2 + 2, y2 + 2], outline=(*accent, 255), width=4)

    if cursor_xy:
        cx, cy = [int(v) for v in cursor_xy]
        draw = ImageDraw.Draw(out)
        draw.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], outline=(*accent, 140), width=3)
        draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=(*accent, 220), width=3)
        arrow = [(cx, cy), (cx + 2, cy + 22), (cx + 8, cy + 16), (cx + 18, cy + 15)]
        draw.polygon(arrow, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))

    return out.convert("RGB")


def render_chapter_card(scene: dict, idx: int, total: int, theme: dict) -> Image.Image:
    """Render an intro or section chapter card in the configured brand palette."""
    accent = hex_to_rgb(theme["accent_color"])
    dark_bg = hex_to_rgb(theme["dark_bg"])
    text_color = hex_to_rgb(theme["text_color"])
    badge_text = hex_to_rgb(theme["badge_text_color"])

    canvas = Image.new("RGB", (WIDTH, TOTAL_H), dark_bg)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([0, 0, WIDTH, 10], fill=accent)
    draw.rectangle([56, 72, WIDTH - 56, VIEWPORT_H - 36], outline=(48, 48, 48), width=2)
    draw.rectangle([56, 72, 66, VIEWPORT_H - 36], fill=accent)

    draw.rectangle([108, 120, 184, 196], fill=accent)
    draw.text((117, 166), theme.get("logo_text", "demo")[:8], fill=text_color, font=FONTS["logo"])

    draw.text((108, 228), scene.get("kicker", "CHAPTER"), fill=accent, font=FONTS["kicker"])
    next_y = draw_wrapped_text(
        draw, (108, 266), scene["title"], FONTS["chap_title"], text_color, WIDTH - 220, line_spacing=10
    )
    draw.rectangle([108, next_y + 18, 280, next_y + 23], fill=accent)

    by = next_y + 54
    for bullet in scene.get("bullets", []):
        draw.rectangle([112, by + 10, 124, by + 22], fill=accent)
        by = draw_wrapped_text(
            draw, (144, by), bullet, FONTS["chap_bullet"], (228, 228, 228), WIDTH - 260, line_spacing=6
        )
        by += 18

    draw.rectangle([0, VIEWPORT_H, WIDTH, VIEWPORT_H + 4], fill=accent)
    draw.rectangle([0, VIEWPORT_H + 4, WIDTH, TOTAL_H], fill=(16, 16, 16))
    draw.rectangle([24, VIEWPORT_H + 16, 148, VIEWPORT_H + 46], fill=accent)
    draw.text((34, VIEWPORT_H + 21), "CHAPTER", fill=badge_text, font=FONTS["badge"])
    draw.text((164, VIEWPORT_H + 18), scene["title"], fill=text_color, font=FONTS["headline"])
    draw_wrapped_text(
        draw, (24, VIEWPORT_H + 56), scene["narration"], FONTS["subtitle"], (215, 215, 215), WIDTH - 60, 4
    )

    prog_w = int(WIDTH * ((idx + 1) / total))
    draw.rectangle([0, TOTAL_H - 5, prog_w, TOTAL_H], fill=accent)
    return canvas


def render_step_frame(
    scene: dict,
    idx: int,
    total: int,
    step_num: int,
    step_total: int,
    screenshots_dir: Path,
    theme: dict,
    zoom_progress: float = 0.0,
) -> Image.Image:
    """Render a browser screenshot with spotlight/cursor, callout card, and 2-line subtitle footer."""
    accent = hex_to_rgb(theme["accent_color"])
    card_bg = hex_to_rgb(theme["card_bg"])
    text_color = hex_to_rgb(theme["text_color"])
    badge_text = hex_to_rgb(theme["badge_text_color"])

    src_path = screenshots_dir / scene["file"]
    raw = Image.open(src_path).convert("RGB").resize((WIDTH, VIEWPORT_H), Image.Resampling.LANCZOS)
    raw = apply_focus_and_cursor(raw, scene, accent)

    if scene.get("zoom_focus") and zoom_progress > 0.0:
        zoom = 1.0 + 0.12 * zoom_progress
        if scene.get("focus_box"):
            x1, y1, x2, y2 = scene["focus_box"]
            zx, zy = (x1 + x2) / 2, (y1 + y2) / 2
        elif scene.get("cursor_xy"):
            zx, zy = scene["cursor_xy"]
        else:
            zx, zy = WIDTH / 2, VIEWPORT_H / 2
        cw, ch = WIDTH / zoom, VIEWPORT_H / zoom
        left = max(0.0, min(WIDTH - cw, zx - cw / 2))
        top = max(0.0, min(VIEWPORT_H - ch, zy - ch / 2))
        raw = raw.crop((left, top, left + cw, top + ch)).resize((WIDTH, VIEWPORT_H), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (WIDTH, TOTAL_H), (0, 0, 0))
    canvas.paste(raw, (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Measure callout card
    card_w = 365
    callout_body = scene.get("callout_body", "")
    callout_title = scene.get("callout_title", "KEY INSIGHT")
    if callout_body:
        words = callout_body.split()
        lines = []
        cur = ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if draw.textbbox((0, 0), trial, font=FONTS["callout_body"])[2] <= (card_w - 36):
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        card_h = 46 + len(lines) * 21 + 12
        cx, cy = choose_callout_corner(scene, card_w, card_h)

        draw.rectangle([cx + 5, cy + 5, cx + card_w + 5, cy + card_h + 5], fill=(0, 0, 0))
        draw.rectangle([cx, cy, cx + card_w, cy + card_h], fill=card_bg, outline=accent, width=2)
        draw.rectangle([cx, cy, cx + 6, cy + card_h], fill=accent)
        draw.text((cx + 16, cy + 12), callout_title.upper(), fill=accent, font=FONTS["callout_title"])
        ty = cy + 38
        for line in lines:
            draw.text((cx + 16, ty), line, fill=(245, 245, 245), font=FONTS["callout_body"])
            ty += 21

    # Bottom 112px subtitle bar
    draw.rectangle([0, VIEWPORT_H, WIDTH, VIEWPORT_H + 4], fill=accent)
    draw.rectangle([0, VIEWPORT_H + 4, WIDTH, TOTAL_H], fill=(12, 12, 12))

    bx, by = 22, VIEWPORT_H + 14
    bw, bh = 96, 30
    label = scene.get("step_label", f"STEP {step_num:02d}")
    draw.rectangle([bx, by, bx + bw, by + bh], fill=accent)
    bb = draw.textbbox((0, 0), label, font=FONTS["badge"])
    draw.text((bx + (bw - (bb[2] - bb[0])) // 2, by + 5), label, fill=badge_text, font=FONTS["badge"])

    phase = scene.get("phase", "DEMO")
    pb = draw.textbbox((0, 0), phase, font=FONTS["phase"])
    pw = (pb[2] - pb[0]) + 18
    px = bx + bw + 10
    draw.rectangle([px, by, px + pw, by + bh], fill=(38, 38, 38), outline=(90, 90, 90), width=1)
    draw.text((px + 9, by + 6), phase, fill=accent, font=FONTS["phase"])

    draw.text((px + pw + 14, by + 2), scene.get("headline", ""), fill=text_color, font=FONTS["headline"])

    counter = f"{step_num} / {step_total}"
    cb = draw.textbbox((0, 0), counter, font=FONTS["counter"])
    draw.text((WIDTH - (cb[2] - cb[0]) - 22, by + 6), counter, fill=(185, 185, 185), font=FONTS["counter"])

    draw_wrapped_text(
        draw, (22, VIEWPORT_H + 52), scene["narration"], FONTS["subtitle"], (225, 225, 225), WIDTH - 44, 4
    )

    prog_w = int(WIDTH * ((idx + 1) / total))
    draw.rectangle([0, TOTAL_H - 5, prog_w, TOTAL_H], fill=accent)
    return canvas


def format_timestamp(sec: float, sep: str = ".") -> str:
    """Format seconds as HH:MM:SS.mmm (VTT) or HH:MM:SS,mmm (SRT)."""
    ms = int(round(sec * 1000))
    hrs, rem = divmod(ms, 3600000)
    mins, rem = divmod(rem, 60000)
    secs, millis = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}{sep}{millis:03d}"


def write_captions(timings: list[tuple[float, float, str]], out_dir: Path) -> None:
    """Export WebVTT and SRT subtitle tracks synchronized to exact scene timings."""
    vtt_lines = ["WEBVTT", ""]
    srt_lines = []
    for idx, (start, end, text) in enumerate(timings, start=1):
        vtt_lines.append(f"{format_timestamp(start, '.')} --> {format_timestamp(end, '.')}")
        vtt_lines.append(text)
        vtt_lines.append("")

        srt_lines.append(str(idx))
        srt_lines.append(f"{format_timestamp(start, ',')} --> {format_timestamp(end, ',')}")
        srt_lines.append(text)
        srt_lines.append("")

    (out_dir / "captions.vtt").write_text("\n".join(vtt_lines), encoding="utf-8")
    (out_dir / "captions.srt").write_text("\n".join(srt_lines), encoding="utf-8")


def write_tutorial_markdown(manifest: dict, out_dir: Path, total_sec: float) -> None:
    """Generate a clean Markdown tutorial guide linking the video and step screenshots."""
    title = manifest.get("title", "Product Demo Tutorial")
    video_cfg = manifest.get("video", {})
    mp4_name = video_cfg.get("mp4_name", "demo_tutorial_recording.mp4")
    gif_name = video_cfg.get("gif_name", "demo_tutorial_recording.gif")
    guide_name = video_cfg.get("guide_name", "TUTORIAL.md")

    mins, secs = divmod(int(round(total_sec)), 60)
    lines = [
        f"# {title} — Visual Tutorial Guide",
        "",
        f"## Full Narrated Video Walkthrough ({mins}m {secs:02d}s • 1280×960 H.264 + AAC)",
        "",
        f"![Walkthrough Preview]({gif_name})",
        "",
        f"- **Narrated MP4 Video:** [`{mp4_name}`]({mp4_name})",
        "- **Subtitles:** [`captions.vtt`](captions.vtt) | [`captions.srt`](captions.srt)",
        "",
        "---",
        "",
        "## Step-by-Step Walkthrough",
        "",
    ]

    step_idx = 0
    for scene in manifest["scenes"]:
        if scene["type"] == "chapter":
            lines.append(f"### {scene['title']}")
            for b in scene.get("bullets", []):
                lines.append(f"- {b}")
            lines.append("")
        else:
            step_idx += 1
            lines.append(f"#### {scene.get('step_label', f'STEP {step_idx:02d}')}: {scene.get('headline', '')}")
            lines.append(scene.get("narration", ""))
            if scene.get("export_name"):
                lines.append(f"![{scene.get('headline', '')}]({scene['export_name']})")
            lines.append("")

    (out_dir / guide_name).write_text("\n".join(lines), encoding="utf-8")


def cmd_build(args: argparse.Namespace) -> int:
    """Render video, audio track, animated previews, subtitles, and tutorial guide."""
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    screenshots_dir = Path(manifest["screenshots_dir"])
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / ".tts_cache"

    theme = {**DEFAULT_THEME, **manifest.get("theme", {})}
    tts_cfg = {**manifest.get("tts", {})}
    if args.voice:
        tts_cfg["voice"] = args.voice
    video_cfg = manifest.get("video", {})
    fps = int(video_cfg.get("fps", FPS))

    scenes = manifest["scenes"]
    total = len(scenes)
    step_scenes = [s for s in scenes if s["type"] == "step"]
    step_total = len(step_scenes)

    audio_chunks = []
    scene_renders = []
    caption_timings = []
    cursor_sec = 0.0
    step_counter = 0

    for idx, scene in enumerate(scenes):
        wav_path = get_cached_tts_wav(scene["narration"], tts_cfg, cache_dir)
        pcm = read_wav_pcm(wav_path)
        audio_sec = len(pcm) / SAMPLE_RATE
        target_sec = max(2.2, audio_sec + 0.55)
        n_frames = int(round(target_sec * fps))
        exact_sec = n_frames / fps
        target_samples = int(round(exact_sec * SAMPLE_RATE))

        if len(pcm) < target_samples:
            pad_len = target_samples - len(pcm)
            lead = min(int(0.15 * SAMPLE_RATE), pad_len)
            padded_pcm = np.concatenate(
                [np.zeros(lead, dtype=np.int16), pcm, np.zeros(pad_len - lead, dtype=np.int16)]
            )
        else:
            padded_pcm = pcm[:target_samples]
        audio_chunks.append(padded_pcm)
        caption_timings.append((cursor_sec, cursor_sec + exact_sec, scene["narration"]))
        cursor_sec += exact_sec

        if scene["type"] == "chapter":
            base_img = render_chapter_card(scene, idx, total, theme)
            scene_renders.append((scene, base_img, n_frames, int(round(exact_sec * 1000)), None))
        else:
            step_counter += 1
            base_img = render_step_frame(
                scene, idx, total, step_counter, step_total, screenshots_dir, theme, zoom_progress=0.0
            )
            if scene.get("export_name"):
                base_img.save(out_dir / scene["export_name"], format="PNG", optimize=True)
            scene_renders.append((scene, base_img, n_frames, int(round(exact_sec * 1000)), step_counter))

    master_wav = cache_dir / "master_narration.wav"
    full_audio = np.concatenate(audio_chunks)
    with wave.open(str(master_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(full_audio.tobytes())

    mp4_path = out_dir / video_cfg.get("mp4_name", "demo_tutorial_recording.mp4")
    cmd = [
        FFMPEG_EXE, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{TOTAL_H}", "-pix_fmt", "rgb24", "-r", str(fps), "-i", "-",
        "-i", str(master_wav),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
        str(mp4_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    fade_frames = 3
    for i, (scene, base_img, n_frames, _, step_num) in enumerate(scene_renders):
        arr = np.array(base_img, dtype=np.uint8)
        if i > 0:
            prev_arr = np.array(scene_renders[i - 1][1], dtype=np.uint8)
            for f in range(1, fade_frames + 1):
                alpha = f / (fade_frames + 1)
                blended = ((1 - alpha) * prev_arr + alpha * arr).astype(np.uint8)
                proc.stdin.write(blended.tobytes())
            hold = max(1, n_frames - fade_frames)
        else:
            hold = n_frames

        if scene.get("zoom_focus") and scene["type"] == "step":
            for f in range(hold):
                zp = f / max(1, hold - 1)
                zimg = render_step_frame(
                    scene, scenes.index(scene), total, step_num, step_total, screenshots_dir, theme, zp
                )
                proc.stdin.write(np.array(zimg, dtype=np.uint8).tobytes())
        else:
            raw_bytes = arr.tobytes()
            for _ in range(hold):
                proc.stdin.write(raw_bytes)

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg mux failed: {stderr_out}")

    write_captions(caption_timings, out_dir)
    write_tutorial_markdown(manifest, out_dir, cursor_sec)

    small_w, small_h = 960, int(TOTAL_H * (960 / WIDTH))
    small_imgs = [r[1].resize((small_w, small_h), Image.Resampling.LANCZOS) for r in scene_renders]
    durations = [r[3] for r in scene_renders]

    if not args.skip_webp:
        webp_path = out_dir / video_cfg.get("webp_name", "demo_tutorial_recording.webp")
        small_imgs[0].save(
            webp_path, save_all=True, append_images=small_imgs[1:], duration=durations, loop=0, quality=82, method=4
        )
    if not args.skip_gif:
        gif_path = out_dir / video_cfg.get("gif_name", "demo_tutorial_recording.gif")
        gif_imgs = [im.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for im in small_imgs]
        gif_imgs[0].save(
            gif_path, save_all=True, append_images=gif_imgs[1:], duration=durations, loop=0, optimize=True
        )

    if args.artifact_dir:
        art_dir = Path(args.artifact_dir)
        art_dir.mkdir(parents=True, exist_ok=True)
        for item in out_dir.iterdir():
            if item.is_file() and item.suffix in {".mp4", ".webp", ".gif", ".png", ".vtt", ".srt"}:
                shutil.copyfile(item, art_dir / item.name)

    print(f"Success! Built narrated demo video ({cursor_sec:.2f}s) in {out_dir}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Inspect rendered MP4 stream metadata via ffmpeg."""
    res = subprocess.run([FFMPEG_EXE, "-i", args.mp4], capture_output=True, text=True)
    info = res.stderr
    has_video = "Video: h264" in info
    has_audio = "Audio: aac" in info
    dur_match = re.search(r"Duration:\s*([0-9:.]+)", info)
    duration = dur_match.group(1) if dur_match else "unknown"
    print(json.dumps({"mp4": args.mp4, "duration": duration, "h264_video": has_video, "aac_audio": has_audio}, indent=2))
    return 0 if (has_video and has_audio) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Video & Tutorial Maker CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-manifest", help="Generate manifest JSON from browser_sandbox screenshots")
    p_init.add_argument("--sandbox-dir", required=True, help="Path to browser_sandbox folder")
    p_init.add_argument("--output", required=True, help="Output path for scenes.manifest.json")
    p_init.add_argument("--title", default="Product Demo Walkthrough", help="Tutorial title")
    p_init.add_argument("--brand-name", default="Product Demo", help="Brand label")
    p_init.add_argument("--accent-color", default="#FF7900", help="Hex accent color (e.g. #FF7900)")
    p_init.add_argument("--voice", default="en-US-AriaNeural", help="edge-tts voice name")

    p_build = sub.add_parser("build", help="Compile narrated MP4, WebP, GIF, captions, and guide")
    p_build.add_argument("--manifest", required=True, help="Path to scenes.manifest.json")
    p_build.add_argument("--output-dir", required=True, help="Directory for output media & guide")
    p_build.add_argument("--artifact-dir", default="", help="Optional artifact dir to copy rendered media")
    p_build.add_argument("--voice", default="", help="Override TTS voice")
    p_build.add_argument("--skip-webp", action="store_true", help="Skip animated WebP output")
    p_build.add_argument("--skip-gif", action="store_true", help="Skip animated GIF output")

    p_verify = sub.add_parser("verify", help="Verify H.264 video and AAC audio streams in MP4")
    p_verify.add_argument("--mp4", required=True, help="Path to MP4 video")

    args = parser.parse_args()
    if args.command == "init-manifest":
        return cmd_init_manifest(args)
    if args.command == "build":
        return cmd_build(args)
    if args.command == "verify":
        return cmd_verify(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
