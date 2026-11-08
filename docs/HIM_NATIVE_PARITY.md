# HiM native-animation mechanism parity: implementation contract

Based on Tom Veuskens et al., **History in Motion**, SCF 2023, especially
§6.1–6.3:
https://doi.org/10.1145/3623263.3623358

**This is a mechanism-parity target, NOT a claim that Fusion Desktop behavior
has been verified on a real model.** There is no guarantee of exact
implementation identity with the authors' undisclosed source code.

## Mechanism checklist

| Original HiM mechanism | Current `fusion-him` path | Validation |
|---|---|---|
| Real parametric source model | `ReferenceSession.open` imports an unsaved `.f3d` document copy | Fusion Desktop required |
| Roll Timeline to feature | `FusionTimelineModel.go`, `ReferenceSession._roll_after` | Stub-tested; Fusion required |
| Increment numeric Feature parameter (Extrude, Revolve, Fillet, Pattern, etc.) | `_model_parameters` and `HiMController._render` set `ModelParameter.value` | Stub-tested; native kernel required |
| Wait for completed frame; adjust parameter increment based on last frame's execution time | `ui/him_frame_clock.js` with `ui/reference.js`, Qt palette `fusionSendData` acknowledgement | Node/V8 helper regression; Fusion timing still requires verification |
| Start at approximately zero but not invalid zero | `core/him_motion.interpolate` (2% initial value) | Unit-tested |
| Pre-feature ghost wireframe, only active Feature opaque | `ReferenceSession` captures genuine BRep edges before the Feature; `core/him_wireframe.py` budgets exact curves; `HiMController._start_ghost_context` draws gray edge graphics and suppresses source Body shading while exact affected faces are drawn opaque. When isolation is not trustworthy, it explicitly falls back to translucent shading | New stub regression tests; Fusion Desktop required |
| Highlight relevant input profile/edge | `FusionTimelineModel.input_geometries` and custom graphics curves | Stub-tested; Fusion required |
| Feature without animation-friendly numeric parameter uses fade/scale | `HiMController._render`, `_fallback`, `_draw_overlay` | Stub-tested; Fusion required |
| Selecting face/edge/vertex filters to relevant historical features | `him_filter`, `ReferenceSession.filter` | Unit-tested algorithm, Fusion integration required |
| Play result in separate viewport preserving original model | Separate reference Fusion instance; unsaved document copy | Integration testing required |
| Restore original expressions on stop/step change/error | `RestoreJournal`, `ReferenceSession.stop`, `HiMController._finish_feature` | Unit-tested; Fusion required |

## Requested visual contract (exCADmple-specific)

For one native Feature at a time, the reference viewport is split into two
separate transient graphics layers:

1. **Context / prior geometry**: `ReferenceSession.frame` rolls the Fusion
   Timeline marker just *before* the feature and captures its genuine BRep
   edge curves once. A persistent, unselectable gray
   `CustomGraphicsGroup.addCurve` group draws those curves. Source model
   bodies in the **unsaved reference document** have their shaded surfaces
   suppressed using reversible opacity overrides (0.001 rather than exact
   zero for Fusion compatibility).
2. **Active Feature / live recomputation**: the real Feature's
   `ModelParameter.value` changes from about 2% toward its actual value.
   Fusion recomputes the native geometry. A separate temporary Custom
   Graphics group displays only feature-owned faces as a solid teal
   overlay, or an independently created new body when identifiable. This
   group updates after each native parameter frame; the background curves
   remain static for that Feature.

On step completion, pause/step switch or error, the original parameter
expressions and every captured body opacity are restored, both Custom
Graphics groups are deleted, and the next Feature may be loaded.

**Never show an edited Body as though the operation created the entire
Body.** If Fillet, Cut, Combine, etc. lack reliable affected-face geometry,
the code retains the established semitransparent context and labels
the mode accordingly. If context exceeds 200 visible bodies or 2,000
edges, a complete exact wireframe is not available; it falls back rather
than displaying an incomplete ghost.

This wireframe presentation is an **exCADmple design choice** built atop
HiM-style native parametric animation; it should not be described as a
pixel-perfect recreation of the original HiM user interface.

## Intentional differences / limitations

- exCADmple adds tutorial steps, editable transcripts and hypothetical testing
  explanations; these are not part of original HiM.
- The reference playback speed is currently exposed as a **multiplier** to
  align with tutorial audio, whereas HiM's paper describes a 2–10 seconds
  per-feature slider. The adaptive frame algorithm initializes at 15–75
  frames for equivalent durations but operates over the tutorial step; if a
  step groups multiple features, the duration is split across them.
- Unrecognized feature kinds remain visible as Timeline states instead of
  fabricating an animation. A missing/invalid parameter may need a visual
  fallback. This is not full coverage of arbitrary CAD features.
- Original HiM's user-facing edit-feature shortcuts and some rendering/
  orchestration details are not a byte-for-byte reimplementation.
- Feature references, component occurrences and large assembly performance
  remain unverified on the specific `fusion.f3d` fixture. Native component
  instances may need extra occurrence-space handling before identical
  wireframe rendering is guaranteed across assemblies.
- An error from Fusion must stop playback and report the failed frame.
  Browser and Fusion responses must not silently mark it successful.

## Minimum real-model release gate

Using the committed `tests/fixtures/real_fusion/fusion.f3d` and
`fusion_example.json` in Autodesk Fusion Desktop:

1. Confirm actual Timeline list and exact per-feature mapping after import;
   record all feature modes (parameter / fade / timeline).
2. On real Extrude/Revolve/Fillet/Pattern features **that exist in this
   model**, inspect successive Fusion parameter values and geometry states:
   they must change during playback, not show a mesh snapshot.
3. Log Fusion rendering latency. Test an expensive Feature and confirm
   fewer, larger increments maintain the configured duration without
   queuing overlapping frames. At least one browser-to-Fusion acknowledgement
   must correspond to a completed native recompute.
4. Verify the gray background is real **BRep edge-only wireframe**, captured
   **before** the active Feature, not a translucent shaded model; verify
   the active Feature-owned surface is opaque and grows as the native
   parameter changes. Test orbit and zoom while playing. Test a Fillet/
   Combine with missing affected faces: it must show the labelled
   translucent fallback, **not** falsely highlight the full Body.
5. Pause mid-feature; replay, reverse, jump to another step, close the
   tutorial and switch documents. Verify all parameter expressions,
   opacity/visibility and Timeline states restore; the original
   `fusion.f3d` checksum remains unchanged.
6. Inspect a Mirror/Combine case: it should use explicit fade/scale, and
   report its mode rather than falsely claiming native parameter animation.
7. Record Fusion version, OS, actual frame timings, pass/fail and relevant
   screenshots for each criterion.

The Python and JS tests do **not** execute the Autodesk CAD kernel, so
passing them cannot establish real-model animation fidelity.
