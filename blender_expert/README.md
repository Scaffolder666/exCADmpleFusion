# NEW: Interactive Blender Extrude Walkthrough (GPU-only reference)

**[Open the new Blender add-on and install instructions](viewport_tutorial/README.md)**

This branch includes a separate `viewport_tutorial/` Blender 4.2+ add-on
with a complete **in-3D-Viewport Extrude demo**, designed after aligning on
expert demonstrations rather than history recording:

- N sidebar has playback controls only (Play/Pause/Previous/Next/Restart/Seek).
- Reference mesh is drawn directly into the real Blender 3D viewport via GPU,
  without any reference mesh in the learner's Scene or Undo history.
- Teaches **Tool → correct Face selection → actually animated Extrude →
  numeric parameter 2.4 → authored Why**, all anchored to 3D reference.
- Your own native Blender modeling and independent Undo continue unaffected.
- Optional explicit practice-base operator creates genuinely extrudable
  topology beside the GPU teacher.
- Includes pure-Python geometry and regression tests, plus CI packaging.

**Do not mix the two add-ons**: the older `excadmple_blender.py` remains as
a reference experiment and is not imported by the new module. Disable the
older add-on when trying the new one.

---

# exCADmple for Blender — ONE viewport, virtual expert + learner

This branch inherits the existing exCADmple Fusion research prototype
and adds a **native Blender add-on** in `blender_expert/`.
Blender lessons use **.blend**, not .f3d. This is not two viewports, not
a stand-alone video, and not a pre-rendered animation.

## What the working prototype is intended to show

You open a `.blend` project, press **Play**, and watch a read-only MASTER
model build step by step in the **same Viewport** as your OWN editable model.
An animated second cursor visibly moves between tool, geometry, numeric
parameter and confirmation targets. A native-looking operation panel explains
the software action, and selected important steps show WHY callouts.

You retain your **real cursor, Blender's real operators, selection, and
Edit Mode**. The teacher layer does not call `bpy.ops` as a modal operator in
your context and never sends synthetic mouse events into your current command.

The demo is **12 operations** that assemble a complete phone stand:
base, rear support, front retaining lip, two braces, and edge beveling.

## Install

1. Open Blender 4.2 or newer.
2. **Edit → Preferences → Add-ons → Install from Disk**.
3. Select `blender_expert/excadmple_blender.py`. Enable the add-on.
4. In the 3D View press **N**, open the **exCADmple** tab.
5. Click **Build .blend phone stand example**. Then **Play**.
6. You can make your own objects in the empty part of the SAME Viewport.
   The teacher objects are offset along X and marked nonselectable.
7. Click **Pause**, **Previous**, **Next**, or **Restart** whenever you want.
8. **File → Save As** saves a regular .blend file with the lesson embedded.
   On reopening it, click **Load embedded .blend lesson**.

## Generate the complete .blend input automatically

You can also build a saved, reusable `.blend` file using Blender's own Python:

```bash
blender --background --factory-startup \\
  --python blender_expert/build_demo_blend.py -- \\
  --output ~/Documents/exCADmple_phone_stand.blend
```

Open that .blend in regular Blender, with the add-on enabled, and click Play.
The script leaves existing learner models alone.

## An existing .blend file of your own

Open any .blend containing mesh objects. Select one or more objects and press
**Reconstruct from selected objects**. This creates a read-only reference
copy, generates object-creation and transform operations, and lets you
play the steps. This fallback is intentionally labelled **reconstructed**.
Without an operation log, Blender .blend cannot recover original human
mouse/keyboard gestures or every modeling decision.

The demonstration works from the included authored metadata more accurately
than from arbitrary object meshes. Capturing Blender operator history is an
important next step for a more general automatic converter.

## Limitations / research prototype status

- The virtual pointer and operation panel are **rendered UI cues**, not a
  second OS mouse, and do not literally activate native Blender modal commands.
  That is deliberate: doing so in one window would steal the learner's input.
- Teacher geometry is assembled at command-completion checkpoints, NOT by
  replaying saved video or HiM-style parameter growth. Each teacher action
  is depicted as tool → selection → value → confirm.
- Audio is not synthesized from imaginary design intent. The included WHY
  statements are *authored scenario annotations*. In a real dataset, use
  original voice / timestamped documentation only.
- This environment lacks Blender Desktop, so the provided Blender runtime
  self-test is not yet verified. Test on your own Blender install:
  `blender --background --factory-startup --python blender_expert/selftest.py`
- Blender's Undo is global for most scene operations, so this teaching layer
  uses dedicated nonselectable teacher objects, not a real concurrent second
  Edit Mode. Fully isolated native command stacks require another process.

## Relevant official APIs

- [Blender SpaceView3D draw handlers](https://docs.blender.org/api/current/bpy.types.SpaceView3D.html)
- [Blender application timers](https://docs.blender.org/api/current/bpy.app.timers.html)
- [Blender Window event_simulate](https://docs.blender.org/api/current/bpy.types.Window.html)
- [Blender data API and collections](https://docs.blender.org/api/current/bpy.types.Collection.html)
