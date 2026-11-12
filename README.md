# exCADmple — authoring plan (design notes)

**Supporting Design Reasoning Through Shared CAD Models** · project overview on [`main`](https://github.com/Scaffolder666/exCADmpleFusion)

This branch keeps the early design notes for how a tutorial is authored: record the designer's process, extract the model per feature, transcribe, cut into steps, review and package.

- The plan itself: [`docs/AUTHORING_PLAN.md`](docs/AUTHORING_PLAN.md)
- Tutorial format at that time: [`docs/EXAMPLE_FORMAT.md`](docs/EXAMPLE_FORMAT.md)
- UI notes: [`docs/UI_DESIGN_NOTES.md`](docs/UI_DESIGN_NOTES.md)

**Superseded.** The plan was first implemented as a command-line workflow on `fusion`, and then as an in-Fusion authoring tool on `authoring-tool`. That tool records while you model, groups features into reasoning steps and stores the tutorial inside the `.f3d`. The code on this branch is an older snapshot; use `fusion-him` or `authoring-tool` instead.

## Branches

| Branch | What it holds |
|---|---|
| [`main`](https://github.com/Scaffolder666/exCADmpleFusion) | Project overview (this research goal, no code) |
| [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him) | **Fusion add-in, version A** (History in Motion style, same viewport). Stable version used for demos. |
| [`authoring-tool`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-tool) | `fusion-him` + the authoring tool: record while modeling, group features into reasoning steps, save the tutorial inside the `.f3d` |
| [`geometry-why`](https://github.com/Scaffolder666/exCADmpleFusion/tree/geometry-why) | `fusion-him` + "Ask why": click the reference model to see the steps behind it |
| [`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion) | Fusion add-in, version B (tutorial overlaid on the Fusion canvas), with the earlier command-line authoring workflow |
| [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) | Earlier design notes for authoring (superseded by `authoring-tool`) |
