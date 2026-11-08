# Real-model validation: `fusion.f3d` (primary HiM acceptance fixture)

**Use this actual researcher-provided Fusion archive for all future end-to-end
`fusion-him` acceptance tests.** The hand-authored `examples/phone_stand.json`
remains a fast UI/mesh-fallback smoke test ONLY and cannot establish that
HiM native feature animation works on complex parametric CAD.

## The source model

- Local filename: `fusion.f3d`
- Size: **324,089 bytes**
- SHA-256: `696ce58b26afc66d68789daa860e8c5ab735522abe2eaa7620b955f1e51c944b`
- Verified offline as a Fusion Design archive containing Design/BRep segments
  and a mechanical assembly preview.
- **Not yet opened or inspected in Fusion Desktop**: feature count, feature
  types, parameter expressions, timeline order and any dependencies are not
  verified. Do not claim parameter animation passed until checked in Fusion.
- This is supplied via the research conversation, **not committed to GitHub**.
  Do not upload or publish the proprietary/binary design without permission.

Keep a private copy at `local-validation/fusion.f3d` under the repository
folder. The `local-validation/` folder is gitignored. The checksum above
distinguishes this specific fixture from another file called `fusion.f3d`.

## Recommended: one-click complex-model demo (synthetic explanations)

1. Update `fusion-him`, then open the exact researcher-provided
   `fusion.f3d` in Fusion Desktop (do not open the bundled Phone Stand).
2. Go to **Utilities → Scripts and Add-Ins → Scripts → +** and select
   `tools/fusion_native_demo`, then **Run**. The script operates on the
   **currently open design**, so check its tab before running.
3. Fusion exports a private reference copy, extracts the actual Feature
   Timeline, and creates **one tutorial step for every real Timeline item**.
   It also produces a small, explicitly hypothetical explanation using the
   operation type, extracted parameters, and recorded dependencies.
4. The generated files are in
   `~/exCADmple-validation/real-fusion/`; **Import**
   `fusion-native-reasoning.excadmple` in the exCADmple HiM palette.
5. Inspect the colored Feature cards (Sketch, Extrude, Fillet, Pattern,
   Revolve, Combine, Move, etc.) and test native animation, input geometry
   highlights, play/pause, reverse, timeline jump, and performance on this
   actual model.

**Interpretation boundary:** explanatory text begins with
`SIMULATED TEST REASONING (not the designer's words)`. It is a
hypothesis/demo stimulus, **not evidence of what the original designer
thought or intended**. Neither synthetic speech nor synthetic timestamps
can be used as think-aloud data for a study. The file remains private.

The original `.f3d` is never saved by this script; the archive embedded
in the tutorial is an exported **copy**. The timeline extractor temporarily
rolls the active design's history but restores its previous marker. If
extraction fails on a complex feature, preserve the error and feature index
instead of substituting the Phone Stand data.

## Alternative: two-stage extraction and packaging

## 1. Inspect and extract in Fusion Desktop

1. Open `local-validation/fusion.f3d` in Fusion using the normal local
   Fusion-archive open/import workflow.
2. Confirm the design is parametric and that the native **Feature Timeline**
   contains items (check count, order, types, sketches, groups and components).
   If there is no usable timeline, report that limitation instead of using
   fabricated features.
3. Run exCADmple on `fusion-him` with this file open. Click
   **Extract tutorial draft…** and save
   `local-validation/fusion.extract.json`.
   The extraction traverses actual timeline states; it can take longer or
   reveal API edge cases on complex designs. If extraction fails, record the
   exact feature name/index and exception; do not silently fall back to the
   Phone Stand demo.

## 2. Package the original archive, without invented narration

Run from the repository root, **outside Fusion Desktop**:

```bash
python tools/build_native_validation.py \
  local-validation/fusion.extract.json \
  local-validation/fusion.f3d \
  -o local-validation/fusion-validation.excadmple \
  --title "Fusion native HiM test" \
  --synthetic-reasoning
```

The script creates **one step for each actual extracted Timeline item**,
using its exact index/name/kind and a synthetic 4-second *test playback
duration* (NOT original authoring timing). It embeds the original `.f3d`
and with `--synthetic-reasoning` generates *explicitly labeled hypothetical
testing captions*. These are **not captured think-aloud, cursor paths, or actual
command activation timestamps**. It does not change the original `.f3d`.

This is a *technical test package*, not a design-reasoning tutorial. For a
future actual tutorial, record the designer's process, voice and reasoning
separately and use the existing authoring pipeline.

## 3. Native HiM acceptance (main test)

1. Import `local-validation/fusion-validation.excadmple` using the exCADmple
   palette's **Import** (do not try importing bare `.f3d` through that button).
2. Verify it opens the **source .f3d model/copy**, matches every step to the
   correct timeline item, and reports unsupported/unmapped features rather
   than animating a random similarly named feature.
3. Find the actual Extrude, Fillet, Revolve, Pattern, Mirror, etc. items in
   **this** model, where present. For supported parameterized features, check
   that **Fusion recomputes native geometry** from temporary parameter
   changes. For unsupported/non-parametric features, report the intended
   visual fade/timeline fallback. Do not assume every listed feature exists.
4. Inspect geometry correspondence: selected faces/edges, local teal input
   or changed surfaces, arrows/command labels. Highlight only credible
   geometry; watch for wrong feature copies, distant annotations and
   occlusion.
5. Test play/pause, playback speed, reverse, repeated replay, random feature
   jumps, selected geometry → relevant history, and **Show more**.
6. Test performance on this model: frame latency, UI freezes, memory growth,
   expensive extraction, and changes in model complexity. Record any feature
   index that stalls or fails and whether the renderer falls back.
7. **Safety:** copy/record original parameter expressions, timeline marker,
   component visibility and body opacity beforehand. After interruption,
   stop, document switch and addon exit, verify they are identical and the
   original `.f3d` was neither modified nor saved.
8. Retest after each change to native playback/geometry guidance; use the
   synthetic Phone Stand only for quick auxiliary UI smoke tests.

Record Fusion version, OS, timeline feature count, feature names/types
actually present, pass/fail, screenshots and error logs. A passing
`python -m unittest discover -s tests -v` run verifies stubs and pure
Python logic, **not Fusion Desktop's kernel/API behavior**.

## 4. Regression commands

```bash
python -m unittest discover -s tests -v
node --check ui/reference.js
```

The native-validation packaging tests use a small in-memory fake extract
for CI; the private 324,089-byte `fusion.f3d` is reserved for the
Fusion Desktop end-to-end acceptance test.
