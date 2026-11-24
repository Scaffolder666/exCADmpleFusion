# exCADmple: Fusion HiM → **In-Viewport Operation Walkthrough**

This is a new experimental branch created from **`fusion-him`**, not from
the previously rejected `fusion-him-operation-walkthrough`. Neither original
branch was overwritten.

## Precise UI contract

**ONE visible, real Fusion CAD viewport.** It contains:

- YOUR editable model, operated with your real Fusion mouse/commands;
- a read-only reference model copied into the same viewport with Fusion
  Custom Graphics, while its `.f3d` parametric history stays in an
  independent, unsaved reference document;
- native HiM sketch-line revelation and feature input/result highlights;
- a **transparent Fusion Palette ON TOP OF THE CAD VIEWPORT**, anchored near
  the current reference feature. This contains an authentic Fusion tool icon
  and spotlight, optional *real recorded operation video* zoom/cut,
  parameter chips and a sourced Why callout. Autodesk's
  `Palettes.addTransparent` is used where supported; a normal floating
  Palette is the fallback.

The **right playback controller** only contains Play/Pause, Back/Forward,
Replay, scrub, speed, and optional 3D Auto-frame. No tutorial text, video,
tool tutorial, or reasoning is visibly rendered there. The old docked
"Tool in Use" educational window is not created.

**The floating teaching card is still an HTML Fusion Palette, not a
second 3D viewport or a video replacing the entire Fusion workspace.**
It is a small, draggable overlay: drag the card's top header to move it,
and click **◎ Follow** to restore automatic feature anchoring. It receives
mouse clicks only inside its own small rectangle; the rest of the CAD viewport
remains fully interactive. When an original video cut is shown, the card
grows; for an operation without footage, it shrinks to reduce occlusion.

## What clicking Play does

Imagine the source step contains both SKETCH and EXTRUDE.

1. **Tool moment (in viewport).** A spotlight appears on the real Fusion
   command's icon/label in the teaching card. The original native ToolGuide
   also promotes the matching command into Fusion's native toolbar. If
   available, the card offers **Try**: an EXPLICIT learner click pauses
   demonstration and launches the actual native Fusion tool on YOUR design.
2. **How moment (in viewport).** When actual operator footage is attached,
   the small viewport video shows the artist using that CAD tool: selecting
   Line, placing points, drawing segments, picking profiles, entering values.
   It automatically seeks to the **source video timestamps** and can zoom
   into the authored location of interest. The video never takes mouse focus
   or replaces the viewport.
3. **Geometry moment (same 3D viewport).** The native HiM renderer continues
   drawing its real source geometry: Sketch segments reveal one at a time;
   Extrude/Fillet/other supported features change using the existing
   reference Feature Timeline and draw input/highlight overlays. The
   tutorial card moves near the active feature when the action changes.
4. **Why moment (at the reference geometry).** Relevant author-provided
   cues appear in the viewport tutorial card, synchronized with narration.
   Hypothetical text automatically created from a bare .f3d is NOT
   represented as the original author's rationale.

The process repeats for each tool inside a step. Only your own operations
enter your model's parametric Timeline. A reference operation does not
enter your Undo History.

**Auto-focus:** the teaching card follows the current feature when the
operation changes. The original HiM Auto-frame checkbox is optional and
off by default; without it, the user's camera is not changed automatically.

## Launch the prototype

1. Switch your local repository to branch
   `fusion-him-viewport-walkthrough`.
2. In Fusion Desktop: Utilities → Scripts and Add-Ins → Add-Ins → choose
   your exCADmpleFusion add-in and Run.
3. The controller appears docked at the right. Open your own active,
   editable Fusion design, then **+ Import** your authored `.f3d`/JSON
   pair, or choose the bundled example.
4. Press **Play**. The floating "exCADmple · In-viewport demonstration"
   card appears **over the CAD canvas**, rather than inside the controller.
5. Watch how the Tool / How / Geometry / Why card changes while the actual
   source Reference Model evolves through HiM.
6. Try constructing your own Sketch/Extrude on your editable model as the
   source tutorial runs. Click **Try** in a Tool moment to pause teacher
   and start the native command for yourself.
7. Pause/scrub/skip in the right controller. Resize/reposition the viewport
   card if it obscures an important part of your design.

**Important:** the bundled Phone Stand is an *illustrative example*;
it has NO original screen video and NO source .f3d from a real author.
Without genuine footage, the How presentation consists of clearly marked
reconstructed operation guidance and whatever original HiM animation is
available. It cannot demonstrate literal historical mouse clicks.

## Add real CAD operation footage (one long video is enough)

Put `example.json`, any referenced `.f3d`, the uncut `session.mp4`
and a `cuts.json` alongside one another. Copy
`examples/walkthrough_cuts_example.json` and replace step IDs and all
timestamps with those from YOUR actual recording.

Then run:

```bash
python3 tools/walkthrough/attach_clips.py \
  --tutorial /path/example.json \
  --recording /path/session.mp4 \
  --cuts /path/cuts.json
```

Open the newly created `example.walkthrough.json` in Fusion.

A cut references **milliseconds in the original MP4**, not a new video
file. Each modeling step can have multiple `walkthrough` moments.
For a `video_focus` use:
`{"x":0.65,"y":0.43,"scale":1.8}`
where x/y are normalized video coordinates. The viewport card will zoom
toward that coordinate, e.g. to show a Line operation or numeric field.

For `excadmple-pair` files generated from existing .f3d, first use the
authoring sidecar that contains explicit feature step IDs, then attach cuts.
The script never overwrites the original .f3d or original tutorial JSON.

## Engineering implementation

- `ui/reference/player.js`: the right-side controller emits throttled
  `viewport_sync` actions to Fusion. The old (hidden) teaching step rail
  still provides legacy audio/transcript synchronization internally.
- `exCADmpleFusion.py`: translates `viewport_sync` to a frame with the
  current source model feature, tool icon, parameters, clip and source cue.
- `core/tutorial/viewport_storyboard.py`: pure-python source-aware
  operation-stage scheduler. Handles several source features per step.
- `core/playback/viewport_presenter.py`: creates one transparent
  floating Palette over the user's viewport, changes its size when video is
  visible and projects source Feature bounding-box centers to screen
  coordinates for visual anchoring; manual dragging can temporarily override
  automatic positioning.
- `ui/viewport_walkthrough/`: the contextual visual spotlight, real
  video-cut playback and 3D reasoning callout, never rendered in the right
  player.
- `core/tutorial/packages.py` and `example_pair.py`: validated local
  movie paths, authored cut times, focus region and reasoning metadata.

## Critical limitations & acceptance tests

1. **Original Fusion Toolbar outline:** The in-viewport tutorial uses
   Fusion's actual tool names/icons and pinned native buttons, but does
   NOT yet draw a pixel-perfect border around the *original* OS toolbar
   icon. Fusion's Palette DOM cannot control native Fusion toolbar pixels.
   A macOS accessibility / transparent spotlight overlay could add this.
2. **Operation demonstration requires real source video for literal UI
   gestures.** The .f3d Timeline alone cannot reveal historic mouse paths,
   true button sequences or author intent. Without footage, source HiM
   geometry remains the graphical demonstration.
3. **No independent second native Fusion operator.** The virtual expert
   does not trigger native commands on the learner's model. The learner
   has their own real mouse/commands and the only editable Timeline.
4. **Video codec / local file access may vary between Fusion's Qt/CEF
   embedded browsers.** The overlay reports if the referenced video
   cannot be played.
5. **Desktop testing still required.** This environment does not include
   Fusion Desktop. Python/JavaScript static checks and pure-Python
   tests cannot confirm that a floating Palette draws/updates correctly,
   Feature recompute works in the inactive source .f3d document, or the
   draggable overlay stays close to the right geometry across displays.

Recommended Fusion Desktop acceptance test: play an authored .f3d with
Sketch and Extrude clips. While the video demonstrates a Line click,
draw your own Line in your own Sketch. Confirm the original learner
Timeline stays clean of reference Features, Pause freezes both HiM and
video, and Auto-frame OFF never moves your camera.

## Static tests

```bash
python3 -m unittest tests.test_viewport_walkthrough tests.test_operation_walkthrough tests.test_packages -v
python3 -m compileall -q core exCADmpleFusion.py tools/walkthrough
node --check ui/reference/player.js
node --check ui/viewport_walkthrough/walkthrough.js
```

GitHub workflow: `.github/workflows/viewport-walkthrough.yml`.
