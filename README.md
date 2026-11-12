# exCADmple

**Supporting Design Reasoning Through Shared CAD Models**

Designers share CAD models and tutorials so others can reuse their work. A shared model gives the final geometry and the modeling steps, but rarely *why* the designer made each decision. Someone who wants to build on it can see how the model was made, yet still struggles to judge which choices to keep and which to rethink for *their own* design goal.

**exCADmple** lets people explore another designer's process and reasoning inside their own CAD workspace. They can play the whole design process or revisit single steps. Each step shows how the model changed and which CAD operation was used, together with the designer's own spoken reasons (think-aloud) as audio and text. Users can follow the example fully or borrow individual steps while developing their own design in the same workspace. The aim is to support learning not only *how to model* but *how to design*.

![Concept sketch: the reference model beside the user's model in the same viewport, with the tutorial player](docs/preview.svg)

*Concept sketch, not a screenshot.*

## How it is used

1. Work on your own design in Autodesk Fusion.
2. Open a tutorial shared by another designer: their `.f3d` with their recorded reasoning.
3. Play the whole process, or step through it: replay a step, jump ahead, or click part of the model to see the steps that made it.
4. Go back to your own design at any time. What to borrow is your decision; exCADmple does not judge your design or recommend answers.

## Where tutorials come from

The designer models in Fusion and thinks aloud while an authoring tool records which features are created and what is said. Speech is matched to features by time, and the designer groups operations into reasoning steps (one reason can cover several operations). The result is stored inside the `.f3d`, so sharing one file shares the reasoning. See the `authoring-tool` branch.

## Status

Research prototype. The Fusion add-in (`fusion-him`) runs in Fusion Desktop. The authoring tool and "Ask why" are implemented and covered by automated tests on a stubbed Fusion API, but not yet tested in Fusion Desktop.

## Branches

| Branch | What it holds |
|---|---|
| [`main`](https://github.com/Scaffolder666/exCADmpleFusion) | Project overview (this research goal, no code) |
| [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him) | **Fusion add-in, version A** (History in Motion style, same viewport). Stable version used for demos. |
| [`authoring-tool`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-tool) | `fusion-him` + the authoring tool: record while modeling, group features into reasoning steps, save the tutorial inside the `.f3d` |
| [`geometry-why`](https://github.com/Scaffolder666/exCADmpleFusion/tree/geometry-why) | `fusion-him` + "Ask why": click the reference model to see the steps behind it |
| [`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion) | Fusion add-in, version B (tutorial overlaid on the Fusion canvas), with the earlier command-line authoring workflow |
| [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) | Earlier design notes for authoring (superseded by `authoring-tool`) |

## Inspiration

Feature-history animation and filtering the history by selected geometry come from *History in Motion* (Veuskens et al., SCF 2023, [DOI](https://doi.org/10.1145/3623263.3623358)). exCADmple's focus is different: how people reuse another designer's expressed reasoning while designing their own product.
