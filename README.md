# exCADmple — Fusion Player (MVP)

**exCADmple: Supporting Design Reasoning Through Shared CAD Models**

An Autodesk Fusion add-in for **exploring a recorded design example while building your own design in the same CAD workspace**. The example has a separate, data-driven timeline; the user's native Fusion feature timeline is never rolled backward.

This repository is the first **technical prototype**, not a completed study system. It does not capture or infer an author's reasoning, execute the original author's commands, or automatically convert videos to structured examples.

## What works in this prototype

- Load a structured example from a plain JSON file or zipped `.excadmple` package.
- Browse steps, play automatically, pause, scrub inside a step, jump backward and forward.
- Display CAD tool, parameters, timed action cues, and the author's recorded explanation (as text).
- Play optional step-level operation videos and/or separate audio, if supplied.
- Show each step's **read-only reference geometry** in Fusion using Custom Graphics. The example's timeline is independent of the user's native feature history.
- Continue working on your own sketches, bodies and features in the same Fusion document; switching example steps does **not** move Fusion's global history marker.
- Temporarily remove reference graphics before saving the document, and recreate them after saving.

The included Phone Stand is **illustrative test data**. It has three mesh snapshots and demo reasoning text but **no genuine designer voice/video**. The Play control still demonstrates step timing and timed cues.

## Install in Autodesk Fusion

1. Download this repository as a ZIP from GitHub and extract it.
2. Make sure the add-in files live together in one folder named `exCADmpleFusion`, including `exCADmpleFusion.py` and `exCADmpleFusion.manifest`. Do not install just the `ui` folder.
3. Open Fusion and create or open a **Design** document.
4. In **Utilities → Scripts and Add-Ins → Add-Ins**, click **+** and select the `exCADmpleFusion` folder. Run the add-in.
5. The **exCADmple** palette appears on the right, loaded with the demo. Select another step to change the read-only mesh in Fusion's canvas, without changing your native features.
6. Use **Import example** to open your own `.json` or `.excadmple` file. If the palette is closed, re-open it through the **exCADmple Player** button (where Fusion exposes the Scripts and Add-Ins toolbar panel) or restart the add-in.

The demo geometry is intentionally shown around **14 cm to the right** of the document origin. It is *reference display*, not an editable solid. You can create your own components/features anywhere in the same document.

**Platform:** Fusion desktop (Windows/macOS), Python API. UI is HTML/CSS/JavaScript, with no server or external library.

## Design example format (version 1)

An example is a JSON object with `format: "excadmple"`, `version: 1`, a `title`, and an ordered `steps` array. Each step provides:

| Field | Purpose |
|---|---|
| `id`, `title`, `duration_ms` | Timeline navigation and playback length |
| `goal` | Design purpose of the step |
| `geometry.meshes` | Read-only mesh snapshots, vertices in **cm**, triangle index triples |
| `operation.tool`, `instruction`, `parameters` | CAD technique and settings |
| `reasoning.text` | Explanation attributable to the author, where available |
| `cues[]` | Time-stamped operation descriptions within a step |
| `media.audio`, `media.video` | Optional **relative** paths to media assets |

See [examples/phone_stand.json](examples/phone_stand.json) for a complete runnable example.

For a portable `.excadmple` package, create a ZIP containing `manifest.json` (the same schema) and the referenced media assets at their relative paths. For example:

```text
phone-stand.excadmple  (ZIP)
├── manifest.json
├── audio/
│   └── step-2.m4a
└── video/
    └── step-2.mp4
```

Video shows how the original designer interacted with Fusion. The app does not move the actual Fusion mouse or click its native toolbar. The canvas mesh reflects the **step's reference geometry**, not every transient mouse movement during the original operation. Media files are played from their local file URI; verify your Fusion WebView allows playback of the specific codec and container on your OS.

**Important:** Reasoning should represent the author’s stated intent, not an unverified AI inference. The package format intentionally assumes the data is prepared upstream; converting recordings into a package is outside this prototype’s research contribution.

## Architecture

```text
exCADmpleFusion.py         Fusion entry point, HTML bridge, save safety
exCADmpleFusion.manifest   Fusion add-in metadata
core/packages.py          Standalone package validation and safe ZIP loading
core/renderer.py          Transient read-only meshes in the Fusion canvas
ui/index.html             Player markup
ui/player.css             UI styling
ui/player.js              Independent timeline, media and cue playback
examples/phone_stand.json Three-step geometry + reasoning example
tests/test_packages.py    Pure-Python package tests
```

Playback changes **only** the reference Custom Graphics group. It does not call `Design.timeline.play()` or modify `markerPosition`. Fusion's real feature tree continues to belong entirely to the user.

## Test

Without Fusion, you can validate the data parser:

```bash
python -m unittest discover -s tests -v
```

Run the **Fusion integration smoke test** manually:
1. Create an empty design and start the add-in.
2. Jump between the three example steps: the sample mesh should change on the canvas.
3. Create your own Sketch and Extrude; navigate the example again.
4. Confirm your own feature history remains unchanged.
5. Save, close and reopen the design to ensure no orphaned transient graphics remain.
6. Import a second example. Then stop/restart the add-in and confirm the palette and reference cleanup.

## Current limitations and next development steps

- No original recording in the demo. Add author-provided media to test synchronized playback.
- CAD tool and parameter demonstrations are presented as metadata/video, **not simulated live native dialogs**.
- The MVP switches reference geometry **at step boundaries**. Smooth within-step geometric animation can be added with timed geometry states.
- Custom Graphics behavior (especially save/reopen, tool interaction, and canvas performance) must be validated in an installed Fusion version; the code has not been run in Fusion here.
- The imported media uses local file URLs. Fusion’s webview/media decoding needs a real-platform check.
- The player is designed for a single active document and does not implement multi-document reference routing.
- A later user study should examine whether access to this explorable precedent changes users' own design reasoning, not merely operation-following accuracy.

## API references

- [Fusion Palette UI](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Palettes_UM.htm)
- [Fusion Custom Graphics](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomGraphics_UM.htm)
- [Fusion Add-In Manifest](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm)
- [Fusion Document Save Events](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_documentSaving.htm)
