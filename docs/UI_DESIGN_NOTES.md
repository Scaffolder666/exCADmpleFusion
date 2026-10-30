# exCADmple UI design notes

## References inspected

- [FuzzyCAD Fusion palette](https://github.com/Scaffolder666/FuzzyCADfusion360/tree/claude/fs-tools-visualization-d9coo9/FuzzyCAD/palette): `index.html`, `palette.css`, `palette.js` and `ARCHITECTURE.md`.
- [MakeAloud: Think-Aloud to Bridge Design-Fabrication Workflows](https://doi.org/10.1145/3800645.3813028), Ritik Batra, Kendra Wannamaker, George Fitzmaurice, Justin Matejka, DIS 2026. [Free PDF](https://justinmatejka.com/publication/makealoud/3800645.3813028.pdf), especially section 3.2 and figures 3–4.

## Adapted from FuzzyCAD

- The **small, light Fusion palette**, rather than a dark, full-screen tutorial dashboard.
- The **list → selected record → linked geometry** pattern. Process steps are the records; the reference geometry appears in the Fusion canvas.
- Semantic typography, readable card borders, restrained blue accent, and a compact viewport visibility control.
- The separation between stored data, panel display, and Fusion native geometry interactions.

We do **not** copy FuzzyCAD's decision resolution controls, mark lifecycle, or scripts. exCADmple users are not asked to Accept, Reject, Follow, or Adapt a step. Users retain control of their own modeling activities.

## Learned from MakeAloud

MakeAloud's Fusion interface shows categorized, source-backed fabrication insights with relevant visual context; its component-specific insights map to CAD elements and offer contextual GIF evidence. Its goal is to transfer situated maker expertise back to designers.

For exCADmple the analogous design requirement is **situated design precedent**:

1. Keep the selected design step and 3D reference in view.
2. Show what was done (operation, actual parameters, optional media).
3. Show *why*, with the source of the explanation (recorded voice, email, meeting, author-written note).
4. Distinguish actual step geometry from a final-model thumbnail, and source-backed rationale from illustrative mockup text.
5. Never make the original sequence prescriptive. Reuse is the user's decision.

We are **not** implementing MakeAloud's AI recommendations, automatic knowledge capture, or maker-to-designer question answering. That is neither the main contribution nor required for this player.

## Remaining implementation gaps

- **Spatial linking to an individual selected component/face** is not yet implemented. Current MVP switches read-only reference geometry for a step, not highlighting native source features; it cannot claim MakeAloud-style in-place geometry selections yet.
- Text provenance is declared by input metadata `reasoning.source`, not automatically verified. Schema values recognized by the current player: `spoken`, `voice`, `transcript`, `email`, `meeting`, `author`, `written`, `mockup`, `demo`. Missing source is visibly marked as such.
- The provided Caster Wheel `.f3d` supports true final CAD geometry, but stage-by-stage original modeling geometry must be exported with Fusion API.
- Actual desktop testing is needed for palette media and transient geometry lifecycle.

## UI smoke test

1. Import `examples/phone_stand.json` and verify three vertical step rows, active highlight, and step switching.
2. Confirm the demo text shows `Illustrative only` and the explanatory label.
3. Verify 3D step geometry status and reference checkbox; switching does not change user's native history.
4. Import a preview-only .excadmple package; verify `Final preview only` and a disabled 3D-step checkbox, not a false claim of reference geometry.
5. Import a package with `reasoning.source: "meeting"` and check the source tag.
6. Playback and scrub keep the current cue and time display synchronized.
