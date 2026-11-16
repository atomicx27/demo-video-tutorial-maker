# Demo Video & Tutorial Maker (`demo-video-tutorial-maker`)

A standalone **Tutorials-as-Code** engine and Antigravity Agent Skill for turning live web app walkthroughs into narrated MP4/WebP/GIF product demo videos, subtitle tracks, and Markdown tutorial guides.

> Also registered globally in Antigravity Skills at:
> `C:\Users\pashi\.gemini\config\skills\demo-video-tutorial-maker\`

---

## Features & Improvements

- **Browser Sandbox Auto-Ingest (`init-manifest`)**: Parses screenshots (`step_*.png`) and HUD accessibility logs (`step_*_hud.txt`) into an editable JSON storyboard.
- **Neural Voiceover TTS with SHA-256 Audio Caching**: Synthesizes voiceover via `edge-tts` (with automatic Windows `System.Speech.Synthesis` offline fallback) and caches normalized 24kHz PCM WAV clips in `.tts_cache/` so re-renders are fast.
- **Exact Audio-to-Frame Sync**: Quantizes each scene's duration to exact integer frames and pads digital silence per scene so narration never drifts out of sync.
- **Screen-Studio-Style Cinematic Focus**:
  - `focus_box`: Dims surrounding UI and highlights the active region in your brand color.
  - `zoom_focus`: Smooth ease-out zoom (`1.0x → 1.12x`) into the active UI target.
  - `cursor_xy`: High-contrast simulated cursor arrow + double click ripple rings.
  - `callout_pos: "auto"`: Places floating explainer cards in the corner farthest from `focus_box` / `cursor_xy`.
- **Chapter Title Cards & 2-Line Subtitles**: Branded chapter cards + bottom step/phase/subtitle bars + exported `captions.vtt` & `captions.srt`.
- **Multi-Format Export**: Outputs `MP4` (H.264 + AAC, `+faststart`), animated `WebP`, animated `GIF`, annotated keyframe PNGs, and `TUTORIAL.md`.

---

## Quick Start

### 1. Install Python Dependencies
```bash
python -m pip install pillow numpy imageio-ffmpeg edge-tts
```

### 2. Generate a Starter Manifest from Browser Screenshots
```bash
python scripts/demo_video_maker.py init-manifest \
  --sandbox-dir "C:\path\to\browser_sandbox" \
  --output "scenes.manifest.json" \
  --title "My App Walkthrough" \
  --brand-name "My Brand" \
  --accent-color "#FF7900"
```

### 3. Build Narrated Video, Captions & Guide
```bash
python scripts/demo_video_maker.py build \
  --manifest "scenes.manifest.json" \
  --output-dir "./docs"
```

### 4. Verify Output Streams
```bash
python scripts/demo_video_maker.py verify --mp4 "./docs/demo_tutorial_recording.mp4"
```

---

## Folder Contents
```text
Demo_Video_Skill/
├── README.md                                 # Standalone guide & CLI usage
├── SKILL.md                                  # Antigravity agent skill definition
├── scripts/
│   └── demo_video_maker.py                   # CLI engine (init-manifest, build, verify)
├── references/
│   └── research_and_best_practices.md        # Open-source research & full manifest schema
└── examples/
    └── sample_manifest.json                  # Sample storyboard demonstrating all features
```
