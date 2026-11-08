# Task for an AI coding agent: test and harden the exCADmple Fusion JSON + F3D integration

Repository: https://github.com/Scaffolder666/exCADmpleFusion
**Work exclusively on branch `fusion-him`.** Do not modify `main`, `fusion`, or `blender`.

## Objective

Verify that an example can be loaded as two side-by-side files rather than requiring an `.excadmple` package:

```
tests/fixtures/real_fusion/
  fusion_example.json
  fusion.f3d
```

The JSON sidecar is committed. The source `fusion.f3d` is a ~324,089-byte binary supplied by the researcher and must be copied into that directory if it is not already in the checkout. Its SHA-256 **must** equal:

```
696ce58b26afc66d68789daa860e8c5ab735522abe2eaa7620b955f1e51c944b
```

**IMPORTANT:** If `fusion.f3d` is absent, explicitly report **fixture missing**; do not create a substitute model, remove the checksum, change the JSON to another file, or pretend that mock tests validate the real model. The repository is public: avoid uploading other private user assets.

## Intended behavior

1. User launches Autodesk Fusion and the exCADmple add-in on the `fusion-him` layout.
2. User selects `fusion_example.json` through **+ Import**.
3. Plugin automatically locates `fusion.f3d` next to it and verifies the optional SHA-256.
4. Fusion imports an *unsaved copy* of that native archive. The original file remains bitwise unchanged.
5. The plugin reads the **actual parametric Feature Timeline**: index, name, type, and available parameter expressions; do not infer true feature order from binary strings.
6. With `auto_generate: true`, it creates one step per real Timeline feature, grouped/color-coded by feature type, with clearly labeled hypothetical design explanations. Transcript/voice is synthetic test data, NOT the original designer's reasoning.
7. It writes `fusion_example.generated.json` alongside the input only if that file does not exist. That file must be editable and reloadable with `auto_generate: false`, with stable exact indices, without overwriting human edits.
8. During playback, use the existing **native HiM** Fusion feature/parameter animation when available; do not switch complex models to interpolated mesh snapshots. Preserve step navigation, reverse playback, selected-geometry filtering, local highlights, arrows and operation labels.
9. Existing `.excadmple` packages and the Phone Stand fallback remain functional.

## Relevant files

- `core/example_pair.py`: new JSON-pair format, generated steps and simulated captions.
- `core/packages.py`: `open_package` dispatch.
- `core/him_reference.py`: native F3D import, mapping and playback.
- `exCADmpleFusion.py`: import UX and reference-session initialization.
- `ui/reference.js`, `ui/reference.css`: timeline and colors.
- `tests/test_example_pair.py`: JSON-pair unit tests.
- `tests/test_native_validation.py`, `tests/test_him_native.py`, `tests/test_spatial_guidance.py`: regressions.
- `docs/JSON_F3D_PAIR.md` and `docs/REAL_FUSION_MODEL_TEST.md`: behavior and limitations.

## Required agent workflow

**First, inspect current branch HEAD and source, rather than trusting prior descriptions.**

1. Check the fixture files and SHA-256. If only the JSON exists, continue with non-Fusion tests but flag missing real-model coverage.
2. Run:
   ```bash
   python -m unittest discover -s tests -v
   node --check ui/reference.js
   node --check ui/player.js
   ```
   Report exact test totals, failing names, tracebacks and root causes.
3. Audit the paired JSON import path for:
   - package circular imports, stale Fusion Python modules, and exceptions swallowed by the UI;
   - second Fusion instance / `ROLE == REFERENCE` requirements;
   - whether JSON loading works in the intended user's reference window;
   - missing model, wrong checksum, renamed/duplicate features, wrong indices and no Timeline;
   - generated JSON fidelity and whether edits to `transcript` actually appear on reload;
   - preservation of audio/TTS, per-feature command labels, arrows, and card color;
   - keeping the original model unchanged when the import, animation or cleanup fails.
4. Fix minimal issues in **`fusion-him` only**, add targeted regression tests, run the full suite again, and commit focused changes. Do not rewrite the product UI or create fake outputs to make tests pass.
5. If a Windows computer with Autodesk Fusion is available, perform the end-to-end test below. If not, state clearly **Fusion Desktop NOT tested**. A cloud browser or a GitHub Actions runner does NOT count as a Fusion Desktop validation.

## Fusion Desktop acceptance sequence (requires real Fusion installed)

- Install complete `fusion-him` add-in, fully restart Fusion.
- Put the two fixture files in the **same local directory**, even if they were cloned from this repository. In the **reference** instance, choose **+ Import > fusion_example.json**.
- Verify import succeeds and reports the original model copy, real total Timeline items, and zero unexplained index mismatches. Log each feature's index/type/name; do NOT assume a predetermined feature count.
- Verify `fusion_example.generated.json` is written and has exactly the real features. Preserve exact original parameters. Edit a transcript and re-import the generated JSON; verify the new text and TTS.
- Play several representative features found in THIS specific model: Extrude, Revolve, Combine, Move, Mirror, etc., where present. Distinguish true parameter-driven geometry recomputation from visual/timeline fallback.
- Check step-to-feature mapping, affected geometry highlight, arrow placement, small command labels, face/edge filter, Show More, Play/Pause/Reverse and random step jumps.
- Interrupt animation in the middle; change steps; close the imported reference document. Verify all modified parameters, visibility/opacity and timeline marker are restored, with no edits to the original .f3d.
- Test performance: latency, time spent importing and exploring a feature-heavy Timeline, crashes and API exceptions.
- Record Fusion version, OS, screenshots, the exact feature index/kind for failures, and pass/fail for each acceptance criterion.

## Completion report format

Give:
- what was actually run (CI vs Fusion Desktop separately);
- exact branch and commit hashes;
- test counts, any remaining failures and fixes;
- `fusion.f3d` present/missing and checksum result;
- real native playback tested/not tested;
- specific blocking bugs and reproduction steps.

Do **not** state "ready" based on GitHub mock tests alone. This is research software and native CAD behavior must be verified in Fusion Desktop.
