# Demo Video & Tutorial Maker — Research & Architecture Reference

This document synthesizes industry best practices and open-source patterns for **"Tutorials-as-Code"** and **Automated Product Demo Generation**.

---

## 1. Benchmark Comparison of Open-Source Tools

| Project | Core Stack | Signature Strengths | Adopted Into This Skill |
| :--- | :--- | :--- | :--- |
| **`shreyaskarnik/argo`** | Playwright + Kokoro/Edge TTS + GSAP Overlays + FFmpeg | Unified `.scenes.json` storyboard; SHA-256 content-addressable TTS audio caching; zone-based callouts; simulated cursors & ripples; fade transitions. | JSON scene manifest, SHA-256 `.tts_cache`, zone-aware callouts, cursor ripples, exact audio-to-frame sync. |
| **`getopenscreen/openscreen`** *(formerly `siddharthvaddem/openscreen`)* | Electron/React + Rust Compositor + Local Captions | Screen Studio-style auto-zoom onto interaction targets, smooth pan easing, background framing, multi-format MP4/GIF/WebM export. | `focus_box` spotlight dimming, `zoom_focus` smooth crop-zoom onto active UI controls, multi-format MP4/WebP/GIF output. |
| **`AnayDhawan/openvidstudio`** | AI Coding Agent + MCP + Playwright + Remotion | Agent-directed planning phase (shot list + brand colors before rendering); real browser capture instead of mockups. | Mandatory Storyboard Planning phase, configurable brand theme tokens, live `browser` subagent capture. |
| **`charnley/example-tutorial-as-code`** | Python + Playwright + Piper TTS + FFmpeg | Pairing browser step transitions directly with spoken narration blocks and chapter structure. | Chapter title cards, strict 1-visual-state-per-step recording, automated `captions.vtt` / `captions.srt` generation. |

---

## 2. Manifest JSON Schema (`scenes.manifest.json`)

```json
{
  "title": "Your App Walkthrough",
  "screenshots_dir": "C:/path/to/browser_sandbox/screenshots",
  "theme": {
    "brand_name": "Orange Business",
    "logo_text": "orange",
    "accent_color": "#FF7900",
    "dark_bg": "#000000",
    "card_bg": "#141414",
    "text_color": "#FFFFFF",
    "badge_text_color": "#000000"
  },
  "tts": {
    "engine": "edge-tts",
    "voice": "en-US-AriaNeural",
    "rate": "+6%"
  },
  "video": {
    "mp4_name": "demo_tutorial_recording.mp4",
    "webp_name": "demo_tutorial_recording.webp",
    "gif_name": "demo_tutorial_recording.gif",
    "guide_name": "TUTORIAL.md",
    "fps": 12
  },
  "scenes": []
}
```

### Scene Types

#### A. Chapter Title Card (`"type": "chapter"`)
- `kicker`: Uppercase accent label (e.g., `"PART 1 OF 3 • ADMIN SETUP"`).
- `title`: Large hero heading.
- `bullets`: Array of 2–4 concise takeaways.
- `narration`: Spoken TTS script for this chapter card.

#### B. Step Capture (`"type": "step"`)
- `file`: Filename inside `screenshots_dir` (e.g., `"step_6.png"`).
- `step_label`: Badge label (e.g., `"STEP 01"`).
- `phase`: Workflow section pill (e.g., `"ADMIN SETUP"`).
- `headline`: Bold title shown in the bottom footer bar.
- `callout_pos`: `"auto"` (recommended — avoids `focus_box`/`cursor_xy`), `"tr"`, `"tl"`, `"br"`, or `"bl"`.
- `callout_title` / `callout_body`: Floating explainer card text (omit `callout_body` to hide the card).
- `focus_box`: Optional `[x1, y1, x2, y2]` in `1280×848` space. Dims everything outside the rectangle by ~37% and highlights the box with an accent border.
- `cursor_xy`: Optional `[x, y]` in `1280×848` space. Draws a crisp pointer arrow + double accent click ripple.
- `zoom_focus`: Boolean (`true` enables gentle `1.0x -> 1.12x` zoom toward `focus_box` or `cursor_xy`).
- `narration`: Spoken TTS voiceover + bottom 2-line subtitle text + `.srt`/`.vtt` cue.
- `export_name`: Optional PNG filename to export as a standalone annotated slide (e.g., `"tutorial_step_01.png"`).

---

## 3. Audio-Video Sync & Codec Best Practices
1. **Normalize every TTS clip first** to `24000 Hz, mono, 16-bit PCM WAV` before measuring duration.
2. **Quantize scene duration to exact integer frames (`n_frames = round(target_sec * fps)`)**, then pad the WAV chunk to `round((n_frames / fps) * 24000)` samples. This prevents progressive A/V drift on long multi-minute walkthroughs.
3. **Export H.264 `yuv420p` with `-movflags +faststart`** and even frame dimensions (`1280×960`, divisible by 16) so videos play natively in Chrome, Edge, Slack, Teams, GitHub, and Windows Media Player.
4. **Always pair `.mp4` with `.webp`/`.gif` + `.vtt`/`.srt`**, because markdown viewers (like GitHub READMEs) auto-play GIF/WebP inline while full MP4 provides spoken voiceover.
