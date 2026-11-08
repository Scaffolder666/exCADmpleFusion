# Two-file Example loading (native Fusion History in Motion)

New in `fusion-him`: an Example may be a sidecar **JSON + .f3d** in
the *same folder*. A separate `.excadmple` ZIP remains supported but is
not required for everyday use.

## Start from a real Fusion model

Put the two files side-by-side:

```
MyExample/
  fusion.f3d
  fusion_example.json
```

Minimal JSON:

```json
{
  "format": "excadmple-pair",
  "version": 1,
  "title": "My native Fusion example",
  "model": "fusion.f3d",
  "auto_generate": true,
  "step_duration_ms": 8000,
  "steps": []
}
```

1. Update the entire `fusion-him` add-in and restart Fusion so that
   Python does not reuse outdated modules.
2. Start exCADmple. Click **+ Import**, select **fusion_example.json**
   (NOT `fusion.f3d`).
3. The add-in finds `fusion.f3d` automatically, imports it into a
   separate unsaved Fusion document, and reads its actual native
   Feature Timeline, including accurate names, kinds, and indices.
4. It generates an editable `fusion_example.generated.json` in the
   same folder. It includes one step per real timeline item and a
   **clearly labeled, hypothetical** explanation for each. The original
   `fusion.f3d` is read-only and never overwritten or re-saved.
5. To customize the tutorial, open `fusion_example.generated.json`,
   edit `title`, `transcript`, `duration_ms`, or grouping of
   `features`, save, then **+ Import** the **generated JSON**.
6. The imported copy uses native HiM feature-history animation rather
   than precomputed Mesh snapshots. Step cards are color-coded by
   the real feature type. Existing spatial highlights, selection
   filtering, and playback controls remain in place.

The generator **does not infer the original designer's intent**.
Synthetic text is marked
`SIMULATED DESIGN EXPLANATION (not the original designer's words)`.
It is test material and not a user-study think-aloud recording.
No artificial mouse paths or per-command timestamps are generated.

## Hand-authored JSON / real transcript

To use a manually edited tutorial, set `"auto_generate": false`.
A step may reference a single feature, or group several:

```json
{
  "format": "excadmple-pair",
  "version": 1,
  "model": "example.f3d",
  "title": "My Example",
  "auto_generate": false,
  "steps": [
    {
      "id": "base",
      "title": "Build the base",
      "features": [{"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"}],
      "duration_ms": 8000,
      "transcript": "I established a stable base before adding the upper geometry."
    },
    {
      "id": "round",
      "title": "Round the edges",
      "features": [2],
      "duration_ms": 9000,
      "transcript": "I rounded these edges to make the transition smoother."
    }
  ]
}
```

For original think-aloud use a transcript and optionally a recorded
audio file in the **same directory**. A global `"audio": "session.wav"`
or per-step `"audio": "step.wav"` makes the actual recording take
precedence over synthetic voice. For timestamped text instead of a
single transcript string, use `"cues": [{"at_ms": 1000, "label":
"..."}]`. `audio_offset_ms` can locate a step within a full recording.

Exact Timeline indexes are preferred to names. Duplicate feature names
without an index are rejected, as are unexpected name/kind changes at
existing indices. The optional `model_sha256` pins the JSON to one
specific model. Model paths are intentionally restricted to the JSON
folder, preventing accidental import of another model.

## Limitations and safeguards

- Fusion's native Timeline is the only source of truth for actual
  names, kinds, and ordering. A raw `.f3d` cannot be fully resolved
  from a filesystem-only test.
- The current package/player limit is **150 steps**. Designs exceeding
  this raise an explicit error; do not silently truncate their history.
- Some features are animated parametrically; others use visual
  fallback/timeline state, as in existing HiM code.
- The original model remains unchanged; exCADmple opens an unsaved
  imported copy. The local JSON is not overwritten; the generated
  JSON is only created if absent.
- JSON pairs are supported in the **History in Motion** (`reference`)
  layout. The existing overlay layout and `.excadmple` packages
  have not been changed.
- The code and mock tests do not replace Fusion Desktop validation.
  Inspect native geometry, whether animation recomputes and restores
  correctly, and any failures with the real `fusion.f3d`.

Regression command: `python -m unittest discover -s tests -v`.
