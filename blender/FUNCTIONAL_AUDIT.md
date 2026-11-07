# exCADmple Blender — Functional Audit (7 Nov 2026)

## Intended research interaction

**One Blender 3D Viewport.** A user keeps modeling their own object while
exploring a series of **curated, pre-authored Design Examples**, one active at a
time. Each example combines the 3D evolution of the reference, operation
details, a passive ghost-pointer, spoken rationale and synchronized text.
The current user design is the stable center of this workflow.

This repository currently contains a **single synthetic Phone Stand demo**.
The full multi-example workflow is a goal, not a shipped feature.

## Functionality matrix

| User-visible capability | Current status | Evidence / caveat |
|---|---|---|
| One viewport with user geometry and animated example | **Implemented as a prototype** | One Scene and camera; reference Collection segregated; headless Blender tests verify user's static mesh is not altered |
| Load curated Phone Stand | **Implemented** | N-sidebar launch; 3 hardcoded reference steps |
| Load and switch among multiple independent design examples | **Not implemented** | No example library, selection UI, reusable example builder, or saved per-example position |
| Scrub and navigate modeling steps | **Implemented, GUI unverified** | Global Scene frame; overlay buttons and layout tested without GUI |
| HiM-like 3D evolution of a reference model | **Partially implemented** | Two extrude shape-key visual reenactments and illustrative support rotation; internal operation catalog is *not* 20 actual design examples |
| Model-anchored ghost pointer with move, click, drag | **Implemented synthetically, GUI unverified** | Scripted world-space points projected through current view, passive visualization only; no real cursor control |
| Real author cursor or original CAD history capture | **Not implemented / out of current scope** | Demo pointer, steps and reasoning are authored, not measured |
| Voice playback | **Implemented at step level** | Three synthetic WAV strips added to Blender Sequence Editor and packed into test .blend |
| Exact speech-to-transcript alignment | **Not implemented** | Captions change at authored frame offsets, not word-level timestamps |
| Reasoning explanation | **Implemented as a concise static note per step** | Not an interactive, structured reasoning graph |
| Learn operation and basic parameter | **Partial** | Operation label and selected extrusion distance; no full tool-button or parameter event replay |
| User can continue modeling while the example plays | **Architecturally supported, desktop validation pending** | Input outside overlay passes through in code; modal input / Blender edit mode must be manually tested |
| Protect learner's existing mesh | **Headless validated for static geometry** | Load, replay and reload do not mutate the tested mesh. Reference collection is unselectable, but not fully immutable via all Blender APIs |
| Independent reference playback clock | **Not implemented — key architectural limitation** | Uses Scene frame range and FPS; these affect the user's own animated objects |
| Resume position independently for each loaded example | **Not implemented** | Follows current Scene frame |
| Actual GUI usability and visual fidelity | **Not yet validated** | Automated Blender run is background-only; GPU overlay, pointer projection and modal focus require desktop test |

## High-priority fixes made in this audit branch

1. **Viewport panel responsive layout**: fit a variable number of cards and
   only include a transcript when it cannot collide with speed controls.
   Parametric unit tests check heights 435–780 px.
2. **Reference isolation by Scene**: resolve the dedicated reference
   Collection via the owning Scene and explicit metadata instead of
   `bpy.data.collections.get(<global name>)`. Supports preexisting older
   demo files by recognizing named reference collections containing our
   object metadata.
3. **Repeated preset load integration coverage**: recreate the current
   reference, verify the user's mesh persists, verify audio is not
   duplicated and verify another Scene's reference remains untouched.

## Highest-priority missing end-to-end workflow

**Example Library → Active Example → Play / Learn → Model → Switch Example →
Continue Model → Return to an earlier Example.**

Minimal viable architecture:

- A registry of several **pre-authored, self-contained** example packages
  (models/geometry sequence, steps, operation metadata, ghost pointer,
  narration/captions, rationale), without automatic history extraction.
- An explicit active example ID; hide inactive references instead of
  destroying or mixing reference objects; preserve each example's position.
- Separate the reference animation clock from Blender's Scene time so
  learner modeling remains independent. Audio must be synchronized with
  the reference clock; don't change `Scene.render.fps` as a playback speed
  shortcut in the long-term architecture.
- One viewport plus a slim example switcher above the HiM-like step timeline.
- A desktop interaction pass: open saved .blend, play, edit a user mesh, orbit
  the view, drag progress, switch examples and repeat, save/reopen.

### Scope boundary

Do **not** expand into arbitrary .blend/.f3d import, automatic recovery of
CAD history, AI video conversion, full 20-operation feature-gallery
presentation or additional viewports to satisfy this phase. Those do not
solve the current research question: reusing multiple designers' reasoning
while pursuing one's own design.
