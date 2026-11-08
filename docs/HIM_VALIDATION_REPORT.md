# Native HiM validation and refinement — 2026-11-08

Scope: `fusion-him` only. Baseline: `72d1860bd72eb9d1e7c25d9b5b01d29e216dcfb1`.
No changes to `main`, `fusion`, or `blender`. The white interface, pair loading,
editable transcripts and multiple-example support are retained.

## Assessment

The reference path imports an unsaved Fusion archive document, maps real
Timeline features, reads registered ModelParameters and changes their values.
It does not substitute mesh interpolation for native reconstruction. Original
expressions are journaled. Prior BRep curves and live affected-face copies are
separate temporary Custom Graphics layers. The latter visualize the native
geometry; they are not pre-rendered animation frames.

| Mechanism | Assessment |
| --- | --- |
| Full model before interaction | Implemented; loading and selecting a step do not send animation frames. Filtering now also waits for Play. |
| Native numeric reconstruction | Registered parameter paths, signed 2% start, reverse/intermediate frames and expression restoration pass stub tests. Actual kernel behavior is unverified. |
| Gray pre-feature wireframe | Implemented with complete-context budgets (200 bodies / 2,000 edges). Requires trustworthy affected faces or an identified new body. Rendering is unverified in Desktop. |
| Feature isolation | Exact face copies update after parameter writes. Missing/failed copies no longer substitute a whole edited body, even in shaded fallback or finished-step guidance. |
| Instant nonnumeric features | Actual Timeline result, no reference-mode fade or scale. Legacy inspect behavior remains separate. |
| Slider and pacing | Fake-bridge tests cover scrubbing, endpoints, continuous transitions and delayed replies; frame-clock tests cover adaptive stepping. Native latency and audio alignment need Desktop review. |
| Explanations | Existing cue/transcript timing retained. Fixture reasoning is explicitly simulated, not evidence of the original designer's intentions. |
| Completion | Full shaded model and removed overlays, including filtered clips ending before the final source feature, covered by automated tests. |
| Stop / interruption | Parameters, opacity and original Timeline marker restore on stop. Deactivation now invokes reference cleanup. Frame errors attempt full overview; restore failures are propagated rather than acknowledged as success. |
| Source archive safety | Pair load and checksum tests pass on the real archive. Import/close use a disposable document and never save the source; Desktop lifecycle still requires observation. |

## Targeted fixes

1. Step-card clicks and geometry filtering select context without autoplay.
   Explicit playback commands remain supported. Re-selecting the current step
   returns to overview, including when an older frame acknowledgement is pending.
2. Reference overlays require exact affected faces or a captured pre-feature
   body set proving that the result body is new. Unsupported isolation leaves
   native geometry visible; it does not color an entire edited part as the feature.
3. Failed BRep drawing or rejected overlay opacity restores source shading,
   removes the ghost and reports a context fallback. Graphics ownership is
   recorded before drawing so exceptions cannot strand an untracked group.
4. Restore failures propagate out of stop and native fallback. An overview is
   not reported as successful when restoration failed. The frame bridge returns
   failure for an errored frame or inactive reference document.
5. Unexpected frame errors restore the full Timeline where possible. Public stop
   restores the captured original marker; internal feature transitions avoid
   unnecessary Timeline resets. Document deactivation cleans up the reference.
6. Corrected the parity checklist's obsolete Mirror/Combine fade requirement.

Two previous assertions explicitly required whole-body highlights without
feature faces. They now assert native visibility without false highlighting.
The instant-Mirror test supplies a genuine-style affected-face stub so it still
checks opaque, unscaled overlay behavior. These expectation changes follow the
isolation bug fix; parameter interpolation and lifecycle assertions remain.

## Reconstruction coverage

These are implemented discovery paths, **not a measured inventory of the real
fixture**. Fusion Desktop must discover and verify which are present and editable.

| Feature | Native numeric candidates |
| --- | --- |
| Extrude | `extentOne.distance`, `extentTwo.distance` |
| Revolve | `extentDefinition.angle`, `angleOne`, `angleTwo` |
| Fillet | Each edge set's radius, start/end radius or chord length |
| Chamfer | Each edge set's distance / distanceOne / distanceTwo (not angle) |
| Hole | Extent distance, hole diameter |
| Shell | Inside/outside thickness |
| Circular Pattern | Total angle |
| Rectangular Pattern | Distance one/two |
| Sweep | Distance one/two |
| Offset Faces | Distance |
| Thicken | Thickness |
| Draft | Angle one/two |
| Thread | Thread length/offset |
| Coil | Height/revolutions |

Only actual nonzero ModelParameters at these paths are animated. No numeric
values are inferred from feature names or tutorial prose. Parameter availability
and feasible lower bounds vary by extent type and topology.

| Instant / fallback category | Behavior |
| --- | --- |
| Mirror, Combine, Split Body/Face, Loft, Move | Immediate actual Timeline result; no fade/scale in reference mode |
| Base, CopyPasteBody, Import/Export, Remove, BoundaryFill, Patch, Stitch aliases | Immediate result when recognized; operation may have no renderable result body |
| Sketch / Construction | Immediate completed Timeline state; no invented growth |
| Numeric kind without suitable parameter (e.g. to-object Extrude) | Instant result with reason |
| Rejected intermediate numeric value / feature health error | Restore original parameters, then labelled instant fallback; a failed restoration is an error and stops playback |
| Unknown kinds | Timeline-only state |
| Missing context, budgets exceeded, unreliable faces or failed graphics | Native shaded context; numeric reconstruction can continue, but exact wireframe isolation is not claimed |

## Automated verification

Environment: Linux x86_64, Python 3.12, Node (local); GitHub workflows use Python
3.11. Autodesk Fusion Desktop and the Autodesk CAD kernel are unavailable here.

Real fixture used: `tests/fixtures/real_fusion/fusion.f3d` (324,089 bytes) with
`fusion_example.json`. SHA-256 before and after testing:
`696ce58b26afc66d68789daa860e8c5ab735522abe2eaa7620b955f1e51c944b`.
The archive structure, pair loading, deferred real-Timeline discovery and
unchanged source bytes pass. The JSON contains no predeclared steps and marks
its autogenerated reasoning as simulated.

Baseline: **162 Python tests passed, no skips**; both JS regressions passed.
After changes: **168 Python tests passed, no skips**; both JS regressions passed.

Commands:

```sh
python -m unittest discover -s tests -v
node --check ui/reference.js
node --check ui/him_frame_clock.js
node tests/test_him_frame_clock.js
node tests/test_reference_scrubbing.js
python -m compileall -q core exCADmpleFusion.py tests
node --check ui/player.js
git diff --check
```

Six added Python regressions inject overlay draw failure, face-copy failure,
restoration failure, frame failure and stop at a nonfinal original marker. The
JS regression additionally checks navigation/filtering without autoplay and a
step selection during a delayed native reply.

## Outstanding Fusion Desktop release gate

**No actual Fusion Desktop end-to-end test was performed.** Passing simulated
API tests is not acceptance evidence for native geometry or visual quality.
Run `docs/HIM_NATIVE_PARITY.md` on the actual pair and record Fusion version,
OS, screenshots, feature-mode inventory and frame timing. Specifically verify:

- Actual Timeline mapping and parameter discovery, forward/reverse geometry
  recomputation, topology changes and solver rejection behavior.
- Gray wireframe and opaque affected-face isolation while orbiting/zooming;
  component occurrence transforms and large assemblies remain unverified.
- Slow-frame acknowledgements, slider/cue/audio alignment, rapid scrubbing,
  pause/resume and switching examples during a pending frame.
- Save/deactivate/close/error cleanup, exact expressions and opacity restoration,
  original Timeline marker on stop and final-model overview on completion.
- Instant Mirror/Combine at real scale and labelled shaded fallback when exact
  affected-face isolation is unavailable.
- Source `.f3d` checksum after the complete Desktop sequence.

The visual acceptance criterion remains open until this Desktop gate passes.

## Auto-focus update

The reference panel now has an unchecked-by-default **Auto-focus** checkbox.
When enabled, each new native feature frames its completed affected-face bounds
(or result-body bounds when faces are unavailable) once, before numeric growth.
It preserves viewing direction and uses smooth camera centering/zoom; it does not
repeatedly overwrite manual orbit on animation frames. Overview fits the complete
model only when enabled. With it disabled, playback leaves the camera alone.
No reliable bounds means no camera change. Component-local bounding boxes in
assemblies remain subject to the occurrence-space limitation above.

The reference panel retains **Try example** and removes the tutorial-draft
creation button. The authoring backend is retained for existing workflows.

Five camera regressions were added: center/direction and margin, missing bounds,
perspective fallback, unchecked behavior and one focus per feature. All **173
Python tests** and both JavaScript regressions pass locally. Fusion Desktop
camera behavior remains unverified. Camera API reference:
https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Camera.htm
