# exCADmple — Autodesk Fusion add-in · version A (History in Motion style)

**Supporting Design Reasoning Through Shared CAD Models** · project overview on [`main`](https://github.com/Scaffolder666/exCADmpleFusion)

Play another designer's recorded design process inside your own Fusion design: the whole tutorial or one step at a time, with the designer's spoken reasons as audio and text. You keep modeling in your own design at any time.
## How version A works

- **Two separate histories, one viewport.** The designer's `.f3d` is opened as its own document (a copy that is never saved), with its real Feature Timeline. It is drawn into *your* viewport beside your model as Custom Graphics. Your Design stays the active, editable document, and nothing is added to your Timeline.
- **History in Motion playback.** The reference Timeline is rolled to each feature, and features with a parameter (extrude, revolve, fillet, chamfer, shell, hole, pattern, …) grow for real: Fusion recomputes the parameter from about 0 to its value. A few operations without a usable parameter (mirror, move, combine, …) use a short illustrative motion, which the panel labels as illustrative.
- **What you see per step.** The model before the step is translucent white with a dark outline. The new or changed faces are teal; the inputs (profile, edges) are blue.
- **Player panel (right).** Play, pause, step back and forward, replay, overall progress, speed and auto-focus. A vertical list of steps shows each step's transcript, audio and tools.
- **Tools.** The tools of each step are pinned to an "exCADmple" panel in the toolbar. A small "exCADmple · Tool" window on the left shows the current tool; **Use** starts it in your design.
- **Filter by geometry.** Select a face, edge or vertex in the reference document's tab to play only the steps that made it.

## Install

1. Download this branch as ZIP and unzip it; keep the `exCADmpleFusion` folder whole.
2. `config.json` must say `"layout": "reference"` (the default on this branch).
3. In Fusion: open or create a **Design**, then **Utilities → Scripts and Add-Ins → Add-Ins → +**, choose the folder and **Run**.

## Load a tutorial

- **+ Import** a JSON file that sits next to its `.f3d` (`"format": "excadmple-pair"`). With `"auto_generate": true`, one step per Timeline feature is generated, with a stand-in reason per step, and saved as an editable `*.generated.json`. See [`docs/JSON_F3D_PAIR.md`](docs/JSON_F3D_PAIR.md).
- `.excadmple` packages are still supported.
- `tools/fusion_demo` is a Fusion script that builds a small test model (Sketch → Extrude → Fillet → Sketch → Extrude → Mirror) and its tutorial.

## Diagnostics and tests

- Every start of the add-in writes `logs/latest.log` (Fusion version, the loaded tutorial, how each feature was played, slow frames, errors). Send it after a test run.
- Fusion Desktop checklist: [`docs/SAME_VIEWPORT_TEST.md`](docs/SAME_VIEWPORT_TEST.md).
- Automated tests run on a stubbed Fusion API (they check the add-in's logic, not Fusion's geometry):

```bash
python -m unittest discover -s tests -v
node tests/test_him_frame_clock.js && node tests/test_reference_scrubbing.js
```

## Code map

```text
exCADmpleFusion.py                 entry point: panels, playback commands, save safety, diagnostics
config.json                        layout: reference (version A) or overlay (version B)
core/playback/him_reference.py     the reference session: opens the .f3d copy, plays and filters it
core/playback/same_viewport.py     draws the reference into your viewport
core/playback/him_fusion.py, him_motion.py, him_filter.py   HiM parameter animation and filtering
core/playback/fast_motion.py, manipulator.py                illustrative motion, arrows and values
core/playback/tool_guide.py        the step's Fusion tools (toolbar panel, tool window)
core/tutorial/                     tutorial files: packages.py, example_pair.py (JSON + .f3d)
core/diagnostics.py                logs/latest.log
ui/reference/                      player panel;  ui/tool/  tool window
tools/                             helper scripts (test model, packaging, transcription)
```

## Branches

| Branch | What it holds |
|---|---|
| [`main`](https://github.com/Scaffolder666/exCADmpleFusion) | Project overview (this research goal, no code) |
| [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him) | **Fusion add-in, version A** (History in Motion style, same viewport). Stable version used for demos. |
| [`authoring-tool`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-tool) | `fusion-him` + the authoring tool: record while modeling, group features into reasoning steps, save the tutorial inside the `.f3d` |
| [`geometry-why`](https://github.com/Scaffolder666/exCADmpleFusion/tree/geometry-why) | `fusion-him` + "Ask why": click the reference model to see the steps behind it |
| [`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion) | Fusion add-in, version B (tutorial overlaid on the Fusion canvas), with the earlier command-line authoring workflow |
| [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) | Earlier design notes for authoring (superseded by `authoring-tool`) |

*History in Motion*: Veuskens et al., SCF 2023 ([DOI](https://doi.org/10.1145/3623263.3623358)).
