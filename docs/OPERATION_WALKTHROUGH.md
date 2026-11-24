# Fusion HiM → Operation Walkthrough

**Research goal:** convert a shared parametric CAD model and (optionally)
recorded modeling/think-aloud footage into a step-by-step, in-CAD walkthrough
that teaches **which tool was used, how it was used on geometry, and why**.

This experiment is based directly on the original `fusion-him` branch. It
does NOT replace HiM, create a second visible CAD viewport, or add the
reference designer's features to the learner's Timeline.

## What changes when you click Play

The original HiM reconstruction keeps running in the same Fusion viewport.
Beside the step list, the new **Operation Walkthrough** tracks the current
step. Within one modeling step it automatically progresses through:

1. **Tool** — identify the relevant real Fusion tool and its actual menu
   path. Your existing ToolGuide pins a real Fusion command in the
   exCADmple toolbar panel. The walkthrough card spotlights that tool.
2. **How** — if author footage is available, show the corresponding *cut*
   from the actual Fusion modeling screen recording. You can enlarge/crop
   the important part of the recording, e.g. a Sketch drawing or numeric
   field. Without footage, the card clearly labels generic instructions
   reconstructed from the Feature kind, NOT original designer actions.
3. **Geometry** — the actual HiM reference highlights related inputs,
   feature results and dimensions. The walkthrough tells you what to
   inspect. Auto Focus can frame relevant geometry if you explicitly
   enable the pre-existing checkbox; otherwise your camera is left alone.
4. **Why** — when authored/recorded explanation is available, the player
   presents the time-aligned transcript and existing audio. Never claim
   inferred geometry reasoning was recorded from the author.

The card has **Previous action, Repeat, Next action**, and individual action
chips. These seek within the current HiM step; Step Back/Forward, scrubbing,
Play/Pause, filtering and "Show more" remain available. Clicking
**Try in my design** pauses the tutorial and calls the REAL native Fusion
command explicitly on the learner's model. The teacher never activates an
operator without a user click.

**Only one Fusion viewport** is visible. The reference is still rendered
via CustomGraphics from an unsaved separate `.f3d` document, and your
editable model remains in your own parametric Timeline.

## Test immediately, without any video

Run this branch as the original Fusion add-in. The included illustrative
`examples/phone_stand.json` autoloads. Click **Play** and observe the new
Operation Walkthrough alongside the existing HiM rendering.

For each step, the card should show the Tool, How and Geometry, plus any
authored illustration text under Why. There is NO pretend video: without a
recording, a clearly labelled placeholder appears.

## Test with an actual CAD recording: use timed cuts, no reencoding

The original video can be *one continuous MP4 recording*. Do not need to
manually produce a video file for every Feature.

Put in the SAME directory:
- the `.f3d` and its `excadmple-pair` `.json` manifest, or an existing
  `excadmple` `.json` example;
- `session.mp4` showing the original author modeling;
- `cuts.json` mapping feature step IDs to portions of that recording.

Example `cuts.json` (all times in **milliseconds**):

```json
{
  "cuts": [
    {
      "step_id": "step-3",
      "video_offset_ms": 15200,
      "video_end_ms": 28000,
      "video_focus": {"x": 0.74, "y": 0.42, "scale": 1.75},
      "walkthrough": [
        {
          "kind": "tool",
          "at_ms": 0,
          "title": "Choose Line",
          "description": "Start Sketch > Line",
          "video_start_ms": 0,
          "video_end_ms": 2200
        },
        {
          "kind": "how",
          "at_ms": 2600,
          "title": "Draw the connected segments",
          "description": "Watch where each line starts and ends.",
          "video_start_ms": 2200,
          "video_end_ms": 8000,
          "video_focus": {"x": 0.43, "y": 0.55, "scale": 2}
        },
        {
          "kind": "geometry",
          "at_ms": 6500,
          "title": "Inspect the completed profile",
          "description": "HiM highlights the profile that was created."
        }
      ]
    }
  ]
}
```

Use the step IDs from your tutorial manifest. For automatically generated
`excadmple-pair` tutorials, first export the generated JSON and edit
the steps so they have stable IDs and explicit moments.

Attach cuts:

```bash
python3 tools/walkthrough/attach_clips.py \
  --tutorial /path/to/model.json \
  --recording /path/to/session.mp4 \
  --cuts /path/to/cuts.json
```

This creates `model.walkthrough.json` beside the original. The source
`.f3d`, video and original JSON remain unchanged. Open the new tutorial
file through Fusion's exCADmple **+ Import** button.

**A cut is a time range in the original screen recording.** The new player
seeks to the specified source times, mutes the film by default (the existing
audio track/narration remains authoritative), and optionally zooms into an
authored point of interest. This prototype does not claim to automatically
infer edit points or exact mouse history from `.f3d` alone.

## What is now implemented

- Native HiM single-viewport reference display, playback/filter/step controls
- Dynamic Tool / How / Geometry / Why phase tracking
- Actual native command names & toolbar menu paths from Fusion's ToolGuide
- A visible and clickable spotlight in the tutorial panel, linked to the
  existing pinned real command button in Fusion's toolbar
- Optional **REAL screen recording** playing only the current source clip;
  authored per-moment cuts, pause/seek/skip, and configurable video crop
- Existing synced reasoning transcript/audio, with distinct authored and
  reconstructed statuses
- Per-operation navigation and explicit "Try in my design" handoff
- Video attachment CLI, schema validation, unit tests

## Still not implemented / not implied

- **Native Fusion toolbar OS-level spotlight**: current spotlight is the
  walkthrough card and the native tool in exCADmple's pinned toolbar. A
  translucent highlight centered on the actual original Fusion toolbar
  button would need a macOS Accessibility/overlay integration, not merely
  a Palette HTML element.
- Exact 3D Sketch draw-stroke replay from `.f3d` alone. With an actual
  operation video, the recorded strokes are visible; without it, the system
  shows a labelled procedural reconstruction and HiM geometry.
- Automatic video segmentation from raw footage without timestamps.
- Continuous head-tracking or automatic viewport movement: existing HiM
  **Auto-focus** intentionally remains opt-in so the learner's camera
  doesn't shift during their own modeling.
- End-to-end testing with Fusion Desktop (not available in this execution
  environment). Test this branch in the actual Fusion app before claiming
  compatibility.

## Regression tests

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q core tools/walkthrough exCADmpleFusion.py
```

All earlier `fusion-him` controls and source models remain on the base
branch for comparison.
