# exCADmple

**Supporting Design Reasoning Reuse Through Shared CAD Models**

exCADmple is an HCI research prototype exploring how people can **learn from other designers' modeling processes and decisions while working on their own 3D designs**.

A finished CAD model shows *what* was made. A conventional tutorial often explains *how* to reproduce it. exCADmple aims to make the **design reasoning behind modeling decisions** available as an explorable reference *inside the design workspace*.

## Research idea

The intended workflow is **design-centered, not tutorial-centered**:

1. **Work on your own design** in a normal CAD/3D modeling viewport.
2. **Open a curated Design Example** relevant to your current problem. Its reference model appears alongside your own work in the same modeling environment.
3. **Explore its design process**: a step-by-step evolving 3D model, CAD functions and parameters, a *visual-only* ghost pointer indicating selections/drags, synchronized narration/transcript, and explanations of *why* decisions were made.
4. **Keep designing**. Learn a technique, borrow or reconsider a design decision, or develop your own alternative without leaving the modeling workspace.
5. **Consult another example** as your design progresses, and revisit earlier examples when useful.

The **user's own design is the continuous activity**. Examples are reusable references, not assignments to copy exactly. In the intended system, several examples can be loaded or revisited, with one active reference playing at a time.

### Three kinds of knowledge

| Layer | What the learner can investigate |
|---|---|
| **Why — Design reasoning** | Motivations, constraints, trade-offs, alternatives and the rationale behind a design decision |
| **What — CAD functions** | Which modeling tools/features and parameters were used |
| **How — Modeling interactions** | How geometry changed, where selections happened and how operations such as Extrude were manipulated |

Each curated example ties these layers to the **same sequence of modeling steps**.

## Interaction concept

- **One 3D viewport**, not split screens or a separate tutorial application.
- **Reference geometry and learner-authored geometry side by side** in the same 3D workspace. The reference is visually distinct and protected from accidental selection.
- An **in-viewport, HiM-inspired step player**: step cards, play/pause, seeking, operation information, speed and short reasoning explanations.
- A **passive ghost-pointer dot** and short trail/click pulse illustrate the example designer's interactions. It **does not control the user's actual mouse**.
- **Synchronized example media** (audio, captions and reasoning) while the user remains free to continue modeling.
- In the longer-term design, an **Example Library / switcher** supports moving among multiple reference models and returning to an earlier example without resetting the user's own design.

## Current proof of concept

The most developed experimental branch is a **Blender 4.5 prototype with a pre-authored, nine-step Phone Stand example**. It demonstrates cumulative geometry evolution, scripted ghost-pointer cues, step-level reasoning, captions and synthetic spoken narration.

| # | Phone Stand step | Design consideration |
|---|---|---|
| 1 | Establish the footprint — Sketch / Extrude | Stability and base size |
| 2 | Choose the viewing angle — form / rotate support | Viewing ergonomics |
| 3 | Add a retaining lip — Sketch / Extrude | Prevent slipping |
| 4 | Round base edges — Bevel | Handling comfort vs. contact area |
| 5 | Cut a charging-cable passage — Boolean | Cable access vs. retention |
| 6 | Add two support ribs — modeled braces | Stiffness vs. material |
| 7 | Pattern four anti-slip pads | Friction without a bigger footprint |
| 8 | Open a back-panel window — Boolean | Weight/material vs. stiffness |
| 9 | Check phone fit with a temporary proxy | Clearance, angle and usability |

The example is **pre-scripted, not a recording of a real designer's CAD session**. The narration is synthesized, and some geometry transitions illustrate an operation rather than replaying a native command. The project does **not** claim to infer authentic design intent from a finished model.

### Implementation and development status

This repository currently keeps experimental implementations in **draft pull requests** rather than the default `main` branch:

| Prototype | Link | Status |
|---|---|---|
| **Blender single-viewport player + 9-step Phone Stand** | [Latest Blender development PR #7](https://github.com/Scaffolder666/exCADmpleFusion/pull/7) · [Blender setup and implementation notes](blender/README.md) | Nine-step geometry/narration pass automated Blender tests; desktop GPU/UI interaction still needs hands-on validation |
| **Autodesk Fusion player** | [Fusion MVP PR #1](https://github.com/Scaffolder666/exCADmpleFusion/pull/1) | Earlier technical spike using read-only example geometry alongside the user's native Fusion history |

For implementation details of the earlier Fusion player, see [Fusion prototype technical notes](docs/FUSION_PROTOTYPE.md).

**Not yet implemented in the Blender prototype:** switching among multiple distinct Design Examples, independently persisting each example's playback position, and a playback clock independent of Blender's Scene timeline. These are important next steps for the research interaction, **not existing features**.

**Out of scope for the current POC:** automatically reconstructing arbitrary CAD histories, converting video into tutorials, or building a general catalog of CAD commands. A small number of intentionally authored examples is sufficient to investigate the interaction.

## Try the Blender prototype

See [blender/README.md](blender/README.md) for installation, demo instructions, test limitations and underlying animation mechanisms. The prototype files are also available through [PR #7](https://github.com/Scaffolder666/exCADmpleFusion/pull/7) and its associated CI artifacts. This is the unmerged development branch; **downloading `main` alone does not include the Blender add-on**.

## Inspiration

The modeling-history animations and vertical playback interface are inspired by *History in Motion (HiM)* ([ACM DOI: 10.1145/3623263.3623358](https://doi.org/10.1145/3623263.3623358)). exCADmple investigates a different design opportunity: **using the modeling process and expressed design reasoning of several examples to support a learner's ongoing design work**, rather than only inspecting a modeling history.

---

**Research prototype — actively evolving.** The goal at this stage is to explore design-reasoning reuse through curated examples, not to deliver a production-ready CAD tutorial platform.
