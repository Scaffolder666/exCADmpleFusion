# Fusion shared-viewport Virtual Expert — test instructions

**This is the primary exCADmple interface experiment.** It reuses the original
`authoring-tool` code to preserve the user's editable Design and the reference
model's independent .f3d Feature Timeline. The learner sees one Viewport, never
two application windows.

## Result you should see

- Left or center: YOUR editable model, native Fusion toolbars and your real mouse.
- In the SAME Viewport: read-only reference .f3d, played by the existing Fusion
  reference reconstruction. Teacher objects are *Custom Graphics*, not
  additional features added to your Fusion Timeline.
- Over the REAL Fusion application: click-through virtual EXPERT pointer
  moving toward tool → reference geometry → parameters → confirmation.
- Brief explanation and reconstructed parameter display near the expert pointer.
- Existing exCADmple player: Play / Pause / Replay / step and audio.
- The teacher overlay never moves your actual cursor. You can edit your model
  during playback and your own Timeline remains the only editable Timeline.

## Install on macOS

1. Checkout `prototype-fusion-native-replay` branch.
2. In Terminal install PyObjC:
   `python3 -m pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz`
3. In Fusion Desktop, **Utilities → Scripts and Add-Ins → Add-Ins → +**,
   choose the repository add-in root and Run.
4. Use the plugin as before; **+ Import** an authored `.f3d` or an
   `.f3d` + `.json` pair. To see real reference geometry, use a model with
   **parametric Fusion history** (not a history-less mesh import).
5. In a separate Terminal:
   `python3 native_ui_replay/virtual_expert_overlay.py`
6. Switch back to Fusion and press **Play** in the exCADmple player. The
   overlay is non-interactive and only visible when Fusion is foreground.
7. Select Pause/Step or create geometry in your own model while teacher plays.

For a first test, start with the existing example under the repository
`examples/`; add an authored .f3d pair to exercise the full parametric
reference behavior.

## Calibrate to your own Fusion window

The default virtual pointer targets are approximate screen percentages.
To position it accurately, first run:

`python3 native_ui_replay/virtual_expert_overlay.py --calibrate`

Follow four prompts (tool, reference model, parameter area, confirm) while
hovering over the appropriate regions. Anchors are saved in:
`~/Library/Application Support/exCADmple/anchors.json`

The expert overlay is a macOS click-through transparent NSWindow covering the
main screen, and does not change the actual Fusion UI. These anchors can be
recalibrated after changing display size, Fusion panel layout, or monitor.

## Distinguish the two experimental modes

- **Shared-viewport** (`virtual_expert_overlay.py`) is designed for the
  apprentice experience and does not take the real mouse.
- **Native UI-driving experiment** (`mac_replay.py`, documented in
  `README.md`) directly operates Fusion's native Extrude/Fillet dialogs via
  PyAutoGUI, demonstrating what is technically possible when the learner is
  NOT modeling simultaneously. It is not the shared-viewport architecture.

## Caveats (do not claim more than the system implements)

This is a **visual virtual operator**, not two simultaneous active Fusion
native command dialogs. The overlay follows real CAD history and tutorial
timings, but displays a reproduced operation panel. The actual learner can
still use native commands normally. When input history or documentation is
absent, the system cannot reconstruct the author's exact mouse gestures
or authentic reasoning. The original authored explanations are displayed
when present.

The shared viewport version uses Fusion Custom Graphics copied from another
Design. Recomputing a non-active reference Design, live overlay alignment,
and behavior during complex active learner commands need real Fusion Desktop
integration testing. Stub tests alone do not establish these results.

## Tests

Pure Python:
`python3 -m unittest discover -s native_ui_replay/tests -v`

Fusion Desktop:
- Play a .f3d reference while using an Extrude on your own model.
- Verify your real cursor remains untouched and your active dialog persists.
- Save your design. It must contain no reference features in its Timeline.
- Pause, replay, skip, and inspect source parameter text in the overlay.
