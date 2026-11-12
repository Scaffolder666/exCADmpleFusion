# exCADmple — Autodesk Fusion add-in · version B (overlay)

**Supporting Design Reasoning Through Shared CAD Models** · project overview on [`main`](https://github.com/Scaffolder666/exCADmpleFusion)

Play another designer's recorded design tutorial inside your own Fusion: the whole tutorial, or replay one step and move to the next. Each step shows how the model changed, which tools were used, the pointer path, and what the designer said (think-aloud), as the original audio or synthetic speech plus text. You keep modeling in the same Fusion window.

> The actively developed Fusion version is **version A** on [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him). This branch keeps version B and the earlier command-line authoring workflow.

## Version B: tutorial over the Fusion canvas

- `config.json` → `"layout": "overlay"` (default on this branch).
- The reference model (recorded per-feature snapshots) is drawn in your canvas beside your model as Custom Graphics, together with an orange ghost pointer and the step title and current sentence in the top-left corner.
- A compact floating panel controls playback (it can collapse to a step bar). Fusion does not allow interactive HTML on the canvas, so the "overlay" is a floating panel plus Custom Graphics.
- Optional: link a step to a body or face of your own model; it is highlighted and other bodies are dimmed for that step.
- This branch also contains an older version A (`"layout": "reference"`) that plays the designer's `.f3d` in a second Fusion instance connected over a local link. It is superseded by `fusion-him`.

Reference graphics are temporary and never enter your Timeline; they are cleared before saving and restored afterwards. Dimmed opacities are restored on step change, save, document switch and add-in stop.

## Authoring (command-line workflow)

1. **Record:** toolbar **exCADmple: Record tutorial**, start a screen recording with your microphone, model and think aloud, then **Stop recording** → `*.session.json`.
2. **Extract:** open the finished `.f3d`, panel → **Extract tutorial draft…** → `*.extract.json`.
3. **Transcribe:** any tool that exports `.srt`, or `python tools/transcribe.py session.mp4 -o transcript.srt` (`pip install faster-whisper`).
4. **Segment:** `python tools/author.py draft.extract.json transcript.srt --session tutorial.session.json --video session.mp4 --id phone-stand --title "Phone Stand" -o annotation.json`. Claude proposes the steps and short titles from feature times, tools and speech; it writes no reasoning. Use `--no-ai` for the rule-based split.
5. **Review:** open `ui/author.html` in a browser, check the steps against the video, adjust and export.
6. **Package:** `python tools/build_package.py draft.extract.json annotation.json transcript.srt --media session.mp4 --source Design.f3d -o phone-stand.excadmple`

Format: [`docs/EXAMPLE_FORMAT.md`](docs/EXAMPLE_FORMAT.md). The bundled `examples/phone_stand.json` and `examples/tablet_stand.json` are hand-written examples, not real recordings.

## Install and test

1. Download this branch as ZIP and unzip it; keep the folder whole.
2. In Fusion: open a **Design**, **Utilities → Scripts and Add-Ins → Add-Ins → +**, choose the folder and **Run**. The example tutorial opens; **Import** opens others.

```bash
python -m unittest discover -s tests -v
```

Not yet tested in Fusion Desktop on this branch.

## Branches

| Branch | What it holds |
|---|---|
| [`main`](https://github.com/Scaffolder666/exCADmpleFusion) | Project overview (this research goal, no code) |
| [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him) | **Fusion add-in, version A** (History in Motion style, same viewport). Stable version used for demos. |
| [`authoring-tool`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-tool) | `fusion-him` + the authoring tool: record while modeling, group features into reasoning steps, save the tutorial inside the `.f3d` |
| [`geometry-why`](https://github.com/Scaffolder666/exCADmpleFusion/tree/geometry-why) | `fusion-him` + "Ask why": click the reference model to see the steps behind it |
| [`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion) | Fusion add-in, version B (tutorial overlaid on the Fusion canvas), with the earlier command-line authoring workflow |
| [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) | Earlier design notes for authoring (superseded by `authoring-tool`) |
