---
name: demo-video-tutorial-maker
description: >-
  End-to-end pipeline for recording live web applications in the internal browser
  and compiling narrated MP4/WebP/GIF demo videos with AI voiceover TTS, chapter
  cards, spotlight focus boxes, cursor click ripples, smart callout overlays,
  SRT/VTT captions, and Markdown tutorial guides. Use when the user asks to
  record a demo video, capture an E2E walkthrough, add voiceover/explainer text
  to a screen recording, or generate a visual tutorial guide for a web app.
---

# Demo Video & Tutorial Maker

Turns any live web application or E2E test flow into a polished, narrated product demo video and visual tutorial guide using the **Tutorials-as-Code** architecture (combining patterns from `argo`, `openscreen`, and `openvidstudio`).

---

## Prerequisites & Dependencies

- **Browser Capture:** Uses the built-in `browser` subagent (`Model: "flash"`) to drive the live site in a `1280×900` viewport and capture one visual state per step.
- **Python Packages:** `pillow`, `numpy`, `imageio-ffmpeg`, and `edge-tts` (with automatic Windows `System.Speech.Synthesis` fallback when offline).
  ```bash
  python -m pip install -q pillow numpy imageio-ffmpeg edge-tts
  ```
- **Reference Docs:** See [research_and_best_practices.md](./references/research_and_best_practices.md) for the full JSON schema and open-source architectural design.

---

## 5-Phase Workflow

### Phase 1: Storyboard & Brand Planning
Before launching the browser:
1. Define the **3-part narrative arc**:
   - *Chapter 1:* Initial state / Admin or Creator setup.
   - *Chapter 2:* Core End-User / Participant workflow (happy path + validation/error check).
   - *Chapter 3:* Recovery, management, and clean teardown.
2. Identify brand colors (`accent_color`, `dark_bg`, `brand_name`, `logo_text`) to match the app's UI theme.
3. Keep each spoken narration clip concise (**8–20 words**, ~1 sentence per visual frame) so pacing stays crisp.

### Phase 2: Granular Live Browser Recording
Invoke the `browser` subagent (`Model: "flash"`) with explicit **one-visual-state-per-step** instructions:
- Set viewport to `1280×900`.
- Pause at critical visual milestones **before** clicking submit so states like filled forms, visible password toggles, open autocomplete dropdowns, error alerts, and confirmation modals each get their own `step_N.png` screenshot in `<subagent-id>/browser_sandbox/screenshots/`.
- Include cleanup steps at the end if testing against a live database.
- Verify visited/blocked origins against the `BROWSER_HOST_FACTS` system message.

### Phase 3: Generate & Refine the Storyboard Manifest
Bootstrap a starter manifest directly from the browser subagent's sandbox:
```bash
python scripts/demo_video_maker.py init-manifest \
  --sandbox-dir "<appDataDir>/brain/<subagent-id>/browser_sandbox" \
  --output "scratch/scenes.manifest.json" \
  --title "Your App Walkthrough" \
  --brand-name "Your Brand" \
  --accent-color "#FF7900"
```
Refine `scenes.manifest.json` (see [sample_manifest.json](./examples/sample_manifest.json)):
- Insert `"type": "chapter"` cards between major sections.
- Set `"callout_pos": "auto"` so floating explainer cards automatically avoid active regions.
- Add optional `"focus_box": [x1, y1, x2, y2]` (dims outside the active area + adds an accent highlight border), `"cursor_xy": [x, y]` (adds pointer + click ripple), and `"zoom_focus": true` (smooth 1.0x→1.12x focus zoom) on key interaction frames.
- Mark 6–12 hero frames with `"export_name": "tutorial_step_XX.png"` for the Markdown carousel.

### Phase 4: Build Narrated Video, Captions & Tutorial Guide
Run the `build` command:
```bash
python scripts/demo_video_maker.py build \
  --manifest "scratch/scenes.manifest.json" \
  --output-dir "docs" \
  --artifact-dir "<appDataDir>/brain/<conversation-id>"
```
This automatically produces:
- **Narrated MP4** (`1280×960` H.264 + 24kHz AAC audio, exact frame-synced voiceover cached by SHA-256 in `.tts_cache/`)
- **Muted Animated Previews** (`.webp` for Antigravity artifacts, `.gif` for GitHub READMEs)
- **Subtitle Tracks** (`captions.vtt` and `captions.srt`)
- **Annotated PNG Keyframes** + **`TUTORIAL.md`**

If presenting in chat as an Antigravity Artifact, create `tutorial_guide.md` in `<appDataDir>/brain/<conversation-id>/` embedding the `.webp` preview, clickable `.mp4` link, Mermaid flowchart, and a `carousel` of the exported `tutorial_step_*.png` files from that artifact folder.

### Phase 5: Verify Outputs
Run the stream verifier before reporting completion:
```bash
python scripts/demo_video_maker.py verify --mp4 "docs/demo_tutorial_recording.mp4"
```
Confirm:
- Both `"h264_video": true` and `"aac_audio": true` are returned.
- Visually inspect at least 2 rendered `tutorial_step_*.png` images via `read_file` to verify callout cards do not cover key UI elements.

---

## Common Mistakes to Avoid
1. **Batching multiple UI transitions in one browser step:** Causes missed intermediate screenshots (dropdowns, filled PINs, modals). Always instruct one visual state per step.
2. **Unsynchronized audio duration:** Never hardcode fixed frame counts when voiceover varies in length; let `demo_video_maker.py` measure each WAV clip and pad exact sample counts per scene.
3. **Embedding workspace paths inside Antigravity Artifacts:** Artifacts can only embed images/media located directly inside `<appDataDir>/brain/<conversation-id>/`. Pass `--artifact-dir` to `build` so files are copied automatically.
