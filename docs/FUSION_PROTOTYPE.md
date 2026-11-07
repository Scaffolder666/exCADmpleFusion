# exCADmple — Fusion Player (MVP)

> **Development reference:** This file preserves the earlier Fusion-specific technical documentation. The current project overview is in [README.md](../README.md), and the nine-step Blender POC is described in [blender/README.md](../blender/README.md). These prototypes use different schemas and are not a single released product.

**exCADmple: Supporting Design Reasoning Through Shared CAD Models**

An Autodesk Fusion add-in for **exploring a recorded design example while building your own design in the same CAD workspace**. The example has a separate, data-driven timeline; the user's native Fusion feature timeline is never rolled backward.

This repository is the first **technical prototype**, not a completed study system. It does not capture or infer an author's reasoning, execute the original author's commands, or automatically convert videos to structured examples.

## What works in this prototype

- Load a structured example from a plain JSON file or zipped `.excadmple` package.
- Browse steps, play automatically, pause, scrub inside a step, jump backward and forward.
- Display CAD tool, parameters, timed action cues, and the author's recorded explanation (as text).
- Play optional step-level operation videos and/or separate audio, if supplied.
- Display a genuine final-model preview bundled in a package when its true intermediate geometry snapshots are not yet available, with an explicit label distinguishing the final preview from per-step geometry.
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

See [examples/phone_stand.json](../examples/phone_stand.json) for a complete runnable example.

For a portable `.excadmple` package, create a ZIP containing `manifest.json` (the same schema) and the referenced media assets at their relative paths. For example:

```text
phone-stand.excadmple  (ZIP)
├── manifest.json
├── audio/
│   └── step-2.m4a
└── video/
    └── step-2.mp4
```

For a real-model mockup, the package may include `source/Caster_Wheel.f3d` and `previews/final.png`. Open the original F3D manually in Fusion and import the exCADmple package from the player. If the package has no per-step meshes, the player shows the final preview and step information but **does not claim to reconstruct the original feature sequence**. Extract the actual step states with Fusion's native API in a later development stage.

Video shows how the original designer interacted with Fusion. The app does not move the actual Fusion mouse or click its native toolbar. The canvas mesh reflects the **step's reference geometry**, not every transient mouse movement during the original operation. Media files are played from their local file URI; verify your Fusion WebView allows playback of the specific codec and container on your OS.

**Important:** Reasoning should represent the author’s stated intent, not an unverified AI inference. The package format intentionally assumes the data is prepared upstream; converting recordings into a package is outside this prototype’s research contribution.

## Step-to-Geometry Linking (Fusion prototype)

This version can **associate an exCADmple design step with geometry in the
currently open Fusion document**. It is especially useful when reviewing a
real source model (such as Caster Wheel) whose complete per-step mesh history
has not yet been exported.

1. Open your **source .f3d document** in Fusion.
2. Run exCADmple and import the corresponding example package.
3. Select a step in the exCADmple sidebar.
4. In Fusion's canvas or Browser, select exactly **one BRep body, face, or
   occurrence**. Make sure Fusion is in its normal **Select** mode, not a
   currently executing Sketch/Extrude command.
5. In the sidebar, expand **Linked CAD geometry** and click **Link selected**.
6. Click another step, then return: the linked body/component now receives a
   temporary, translucent blue overlay. A face link currently highlights its
   **parent body** (not only the face).
7. Click **Locate in Fusion** to perform precise native selection of the linked
   object, including an individual face. Click **Unlink** to remove its link.

This functionality uses Fusion's `UserInterface.activeSelections`,
`entityToken`, `Design.findEntityByToken`, and
`CustomGraphicsGroup.addBRepBody`. The overlay never changes body appearance,
opacity, parameter values, or the native feature timeline. **Locate** does
replace the current Fusion selection *when you explicitly click it*, not on
every timeline step.

**Prototype limitations:**

- Bindings are **in-memory and lost when you stop/restart the add-in or import
  a different example**. They are not written to the F3D file, shared example
  package, or GitHub. A save/reopen cycle may require rebinding.
- Tokens resolve within the same design, not arbitrary other copies of the
  model. When Fusion reports multiple matches for an entity (e.g., after a
  face splits), the add-in asks you to rebind rather than guessing.
- Occurrence highlights currently include BRep bodies in that occurrence,
  not mesh bodies or recursively all nested child occurrences.
- Face links use a parent-body overlay; exact face selection is through
  **Locate**. Assembly proxy transforms require a desktop test.
- Users must manually identify correspondence between source geometry and
  placeholder design steps. This does **not** reconstruct the author’s original
  modeling process or rationale from the F3D.
- The original file's geometry may be changed independently by the user;
  the stored link can become stale after topology changes. Geometry links in
  this prototype are for authoring/example inspection, not a final stable
  cross-file reference format.

**Caster Wheel smoke test:** load the original Caster Wheel F3D and its
preview-based `.excadmple` package. Bind one actual wheel body to a step.
Switch steps, verify the blue spatial highlight and that **Locate** selects
the wheel body. Confirm **Play** changes only the reference step; the native
Fusion history marker does not move. Save and reopen, and confirm no orphaned
Custom Graphics remain. Do not treat preview-based placeholders as extracted
timeline features.

## Focus Mode: dim the rest of the assembly

The **Linked CAD geometry** inspector now includes **Focus on linked
geometry**, enabled by default for manually linked source geometry.

When you switch to a step with a valid bound body/face/component, exCADmple:
1. restores previously modified opacities;
2. leaves the selected body, its parent body (for face links), or selected
   component's bodies at their existing opacity;
3. dims unrelated, writable native BRep and mesh bodies to **24% opacity**;
4. draws a temporary, low-opacity blue highlight on the linked BRep geometry.

Uncheck Focus on linked geometry to restore all original opacity values and
continue with the temporary blue highlight alone.

### Display safety

Following FuzzyCAD's opacity-owner model, exCADmple reads and records every
body's original numeric opacity *before* applying dimming, does not override
already-more-transparent bodies, restores on step changes, on package
replacement, on add-in shutdown, on document deactivation, and **before
Fusion saves**. If restoration fails during `documentSaving`, the handler
requests cancellation of that save rather than silently serializing the
wrong appearance.

Native opacity overrides temporarily affect Fusion's *document display
properties*. They are not an independent post-processing layer. An OS crash,
unexpected Fusion termination, failed add-in unloading, conflicting add-in,
or API error may still require manual opacity restoration. **Test on a copy
of the model** until desktop behavior is verified.

The implementation protects the *native source body* of a selected component,
including every occurrence that shares that source geometry. This is safer
than dimming the selected instance accidentally, but means repeated copies
of the same component can also remain opaque. This version does not
independently fade separate instances of the same source component. Nested
occurrence children are excluded from dimming when the parent assembly is
the focus.

Some appearance overrides, active-component visibility settings, and linked
external geometry can make the actual perceived opacity differ from 24%
(see [Fusion BRepBody.opacity](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_BRepBody_opacity.htm)).
Dimming is bounded to at most 250 background native bodies per session.

### Test a real assembly

1. Make a **copy** of Caster Wheel F3D.
2. Select one native BRep wheel body, link it to a step, leave Focus checked.
3. Verify the selected wheel remains visually clear; surrounding fork/mount
   bodies become translucent.
4. Change steps and confirm original opacities return, then focus transfers.
5. Uncheck Focus and verify all background opacity values restore exactly.
6. Re-enable Focus, save the copy, close and reopen it. Confirm original
   appearance is preserved and no residual ghost highlights remain.
7. If other Fusion add-ins modify appearance (including FuzzyCAD), deactivate
   those tools during this test to avoid competing opacity owners.

Pure-Python tests in `tests/test_focus.py` verify opacity restoration
and failure handling without Fusion; native viewport rendering and
document lifecycle still require a Fusion desktop smoke test.

## v0.5 — In-canvas animated Extrude (experimental)

The reference player now accepts a **precomputed, non-destructive 3D Extrude
animation** on an example step. Select the first Phone Stand step and press
**Play**, or drag the step's progress slider. A read-only Custom Graphics
mesh grows from the sketch footprint to the full extrusion in the Fusion
canvas, while the playback panel continues to show operation details and
reasoning. **Pause** freezes the current reference shape; completing the
step restores the finished reference mesh.

The `animation` field is independent of the user's native CAD history:

```json
{
  "animation": {
    "type": "extrude",
    "profile": [[0,0,0],[10,0,0],[10,8,0],[0,8,0]],
    "direction_cm": [0,0,0.7],
    "cap_triangles": [[0,1,2],[0,2,3]],
    "context_meshes": []
  }
}
```

All distances are **centimeters**, Fusion's internal unit. The profile
is ordered around its perimeter; cap triangles index into profile vertices.
The animation constructs a triangular prism of the chosen partial length.
The demo is deliberately a simple convex quadrilateral.

**Technical boundaries:** this is a visual extrusion preview, **not an
animated modification of a native Fusion ExtrudeFeature**. It does not yet
support Join/Cut Boolean updates, multiple profile loops/holes, taper, arcs,
Revolve, Fillet, or robust surface-to-feature provenance. Users cannot infer
that an animation corresponds to real source geometry unless its package
was generated from the actual source's feature/profile metadata. Timeline
events are throttled to approximately seven Custom Graphics redraw requests
per second, not video-grade frame rate. Fusion desktop performance remains
untested. Frame drawing uses local Fusion API events; all native geometry,
native parameter values and the native history marker remain unchanged.

The Caster Wheel package from our earlier mockup contains **no extracted
feature animation**, so playback there still shows the existing preview
and step metadata. To animate an actual Caster Wheel operation accurately,
the next importer must inspect its Fusion feature history and extract the
corresponding original profile, feature parameters and before/after context.
For curved/circular profiles or Boolean operations it needs a more general
meshing strategy than this first polygonal extrusion implementation.

### Relation to History in Motion

Veuskens et al. (SCF 2023), [History in Motion](https://doi.org/10.1145/3623263.3623358),
describe: feature filtering by selected faces/edges; progressive parameter
updates for Extrude/Revolve/Fillet/Patterns; custom fades for operations
without parameters; and an animation renderer isolated from the source
CAD model. Their proof of concept used **two Fusion instances connected
over WebSockets** because the native Fusion UI did not offer the additional
interactive 3D viewport they needed.

This MVP reuses the **animation principle**, not their source implementation:
it renders transient meshes in the same Fusion canvas, from validated data,
instead of changing native feature parameters in a second Fusion copy. It
therefore provides a safe minimal path for playback while leaving the
harder feature-dependency extraction and robust operation reproduction to
subsequent work.

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
