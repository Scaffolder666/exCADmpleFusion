# exCADmple — Blender In-Viewport Extrude Walkthrough

**Branch:** `blender-viewport-extrude-walkthrough` (from
`prototype-blender-native-replay`). This version is a SEPARATE Blender
add-on. It does not overwrite the prior prototype or touch Fusion.

## Exact interaction contract

**ONE real, native Blender 3D Viewport.**

- **Virtual Expert:** teacher is drawn with Blender `gpu` in
  `SpaceView3D.draw_handler_add(..., POST_VIEW)`, plus actual
  world-to-screen projected tool, geometry and reasoning annotations in
  `POST_PIXEL`.
- **Learner:** your own Blender mesh and **real Blender tools** continue
  to operate normally. No modal operator, synthetic clicks, or UI capture
  from the expert. You can select, orbit, edit, extrude and undo your
  own work independently.
- **Side N panel:** **PLAYBACK ONLY** — Play/Pause/Previous/Next/Restart,
  Seek and Speed. No teaching card or tutorial transcript in the sidebar.
- There are **zero expert Scene objects**. The expert is GPU drawing only,
  so playback is absent from both the Object Outliner and learner's Undo.
- An optional **practice base** is made with ONE explicitly user-invoked
  Blender operator. The practice base is genuinely editable and undoable.

## First demo: actually showing HOW to extrude

A phone stand base and rear strip are represented by real, manifold topology
in the **practice mesh**. The yellow face is the *actual* selectable
rear-top face; it is not just a colored patch over one huge top polygon.

| Moment | What user SEES IN the 3D viewport |
|---|---|
| 1 Tool | A prominent **E / Extrude Region** tool spotlight, including Edit Mode and Face Select shortcut |
| 2 Face | The specific real rear-top face highlighted in orange |
| 3 Extrude | The selected 3D face **continuously rises** along Z, while translucent wall geometry, its edges and a directional arrow form |
| 4 Parameter | A localized **Distance 2.4 / Enter** callout next to the 3D support |
| 5 Why | An authored example design-reasoning note next to the resulting reference geometry |

The reference model is offset to **X +4.6**, and your own actual editable
model remains around the origin. You can rotate/zoom the REAL viewport as
the virtual expert moves. When the video stops, the reference remains
visible; Previous, Next and Seek can revisit any intermediate frame.

**No recording and no Feature History are prerequisites.** For this MVP
the sequence, dimensions, and reasoning are explicitly authored. The
reason is labelled *Authored demo rationale*, never "recovered from
the designer". The teacher doesn't execute real Blender commands in
the user's editable scene.

## Install, run, and model along

### Installing Blender 4.2+

From repository root:

```bash
cd blender_expert
zip -r /tmp/excadmple_viewport_tutorial.zip viewport_tutorial \
    -x '*/__pycache__/*' '*/tests/*' '*blender_selftest.py'
```

In Blender, use Edit → Preferences → Add-ons and install the ZIP as a
legacy add-on (Blender 4.2: menu **Install from Disk / Install Legacy
Add-on**, wording can vary). Enable
**exCADmple: In-Viewport Operation Tutorial**. Do **not** enable the older
exCADmple virtual-expert add-on simultaneously, as both use the same
sidebar category.

Alternatively, copy `viewport_tutorial/` into your user scripts
`addons` directory and enable the add-on by name.

### Playing and following along

1. Open an ordinary Blender project and enter 3D View.
2. Press **N → exCADmple**. Only playback controls live here.
3. Press **Play**. The **virtual reference base** appears to the right
   of your workspace, with tool callouts anchored to the reference 3D
   geometry in the *same viewport*.
4. If both sides are not visible, press **F3** and search
   **exCADmple: Frame Both Models**. This ONLY changes camera framing
   on your explicit request; teacher playback never automatically
   hijacks your camera.
5. For a ready-to-extrude learner mesh, press **F3** and search
   **exCADmple: Create Practice Base**. This is the ONLY action in this
   demo that creates a real object. (If the default Blender cube blocks
   the base, hide/delete that cube yourself.)
6. Select YOUR practice base → Tab (Edit Mode) → **3** (Face Select,
   number row, *not* numpad) → select the small top face behind the main
   platform → press **E** → type **2.4** → Enter.
7. Keep the expert running in parallel, or Pause to practice. **Undo**
   (Ctrl+Z, or Cmd+Z as configured) removes YOUR commands, not the
   teacher's reference animation.
8. Use **Previous/Next** to jump between Tool/Face/Extrude/Parameter/Why;
   **Seek** scrubs the real extrude growth even backwards.

All demonstration elements are **in Blender Viewport drawing**, not a
second video panel or HTML viewport.

## Tests

Pure Python, no Blender needed:

```bash
python -m unittest discover -s blender_expert/viewport_tutorial/tests -v
python -m compileall -q blender_expert/viewport_tutorial
```

Live Blender test:

```bash
blender --background --factory-startup \
  --python blender_expert/viewport_tutorial/blender_selftest.py
```

For the actual UI you must test with Blender Desktop. Background mode
cannot verify GPU drawing or whether Viewport annotations overlap native
controls in the current workspace layout.

## What we deliberately did NOT build yet

1. **No automatic history reconstruction** from arbitrary .blend files.
2. **No expert operation recorder** or synthetic mouse.
3. **No original video cuts yet.** This MVP directly visualizes the
   operation in the 3D scene. Real screen clips may be added later if
   genuine UI clicks or dialog interactions require additional footage.
4. **No actual Blender Toolbar button outline yet.** The in-viewport
   shortcut/tool spotlight is truthful, but not a pixel-perfect mask
   around the native toolbar button. The native toolbar is a separate
   UI Region, unlike 3D draw callbacks.
5. **No automated assessment of learner success.** The user's own
   modeling actions are free, not graded or captured.
6. This is a **single-operation MVP**. A generalized authoring system,
   Sketch/Bevel/Loop Cut libraries, and importing existing reference
   designs are subsequent milestones.

## Why GPU-only teacher?

The old `prototype-blender-native-replay` built its expert by creating
Blender mesh objects and adding/removing Bevel modifiers during playback.
Those were read-only to the learner but still lived in the same Scene.
This new implementation changes that: it **only draws the reference
geometry**, so timer ticks and seeking change no Scene datablocks.
The explicit **Create Practice Base** command is a learner-initiated
Undoable action, independent from teacher playback.

Relevant Blender APIs:
- [SpaceView3D draw handlers](https://docs.blender.org/api/4.2/bpy.types.SpaceView3D.html)
- [GPU draw module](https://docs.blender.org/api/4.2/gpu.html)
- [Application timers](https://docs.blender.org/api/4.3/bpy.app.timers.html)
