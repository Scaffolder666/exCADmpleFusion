# exCADmple — Fusion REAL UI Replay (macOS)

This branch extends the existing `authoring-tool` prototype. The original Fusion add-in
is untouched. **This experiment builds a complete phone-stand model through Fusion's
own Extrude and Fillet dialogs and visible macOS mouse movement.** It is *not* the
HiM geometry animation from the baseline.

## What is actually demonstrated

A three-sketch phone stand is prepared as a disposable `.f3d`. The native
UI replay then performs, in **real Fusion Desktop**:

1. Select base sketch profile → launch the **native Extrude** dialog with `E`
   → enter `8 mm` in Fusion's actual Distance field → confirm.
2. Select tall back-support profile → **Extrude 6 mm** → confirm.
3. Select short front-lip profile → **Extrude 5 mm** → confirm.
4. Select a solid edge → launch the **native Fillet** dialog with `F`
   → enter `2 mm` → confirm.

You see the macOS cursor travel between the viewport and dialogs; the Fusion
Timeline receives actual native features. No fake parameters, SVG geometry growth,
or custom substitute commands. Sketches are pre-prepared with the **real Fusion API**
to make the first experiment repeatable. The experiment does **not** claim to
reconstruct arbitrary past mouse clicks from an original `.f3d`.

## Setup — one time

1. On a **Mac with Fusion Desktop**, install Python 3 and PyAutoGUI:
   `python3 -m pip install pyautogui`.
2. System Settings → Privacy & Security → Accessibility → permit Terminal,
   iTerm, or the app launching Python. Optionally allow Screen Recording
   to capture evidence.
3. In Fusion choose **Utilities → Scripts and Add-Ins → Scripts → +**,
   and select `native_ui_replay/FusionStarter/`. Run **FusionStarter**.
   It creates a new Fusion document and exports
   `~/Documents/exCADmpleNativeReplay/PhoneStand_STARTER.f3d`.
4. Place Fusion on the **primary display**, maximize it, set the **Design / Solid**
   workspace and an isometric camera. Make sure **all three sketch profiles
   are visible and selectable**. Do not use a sketch edit mode or an active
   command at the start.

## Calibration and first full build

From a separate Terminal in this folder:

```bash
python3 mac_replay.py --teach --screenshots
```

The guided calibration performs **the actual complete native build** while
asking you to hover over four selections and the two numeric input boxes.
You need to inspect the model after each step: macOS Accessibility / Fusion
UI control positioning varies by version and display. Coordinates save to
`fusion_native_points.json`, locally and untracked.

**Important:** Do not save the completed model over the starter. Calibrating
on the final geometry will not work because the next build needs the sketches.

## One-click full replay

Reopen the unchanged **PhoneStand_STARTER.f3d** from the exported file.
Use exactly the same viewport orientation, window size and sketch visibility.
Then:

```bash
python3 mac_replay.py --dry-run
python3 mac_replay.py --play --screenshots
```

After a single confirmation in Terminal, all **four native modeling operations**
run without further prompts. Watch Fusion, not Terminal. Screenshots are saved
to `native_ui_replay/evidence/` if you enabled them. The result is an editable,
actual Fusion model; you can save it as a separate `.f3d`.

For slower Macs: `python3 mac_replay.py --play --slow 2`.

## Safety and known limitations

- Only run on disposable designs. Moving the mouse to the **upper-left corner**
  triggers PyAutoGUI's emergency stop; Ctrl-C in Terminal also stops playback.
- Coordinates are **not portable** between screens, Fusion layouts, version
  changes, camera positions or display scales. Recalibrate after such changes.
- The first attempt might fail if a sketch is occluded, hidden, or Fusion
  opens a modal in an unexpected state. Restart from the untouched starter.
- The script does **not** detect whether Fusion created the correct feature.
  Inspect the model and the four new features in the Fusion Timeline.
- The original `authoring-tool` branch is still available and unchanged,
  with recording, geometry playback and explanations. This experiment
  focuses deliberately on real Fusion operation playback.
- The Mac / Fusion Desktop behavior has **not been executed in the development
  container**. Python syntax and dry-run plan are testable, but your local
  Fusion test is required to establish actual compatibility.

## API references

- [Autodesk Fusion Commands](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Commands_UM.htm)
- [Native CommandDefinition.execute input is ignored](https://autodeskfusion360.github.io/FusionAPIReference/Fusion_API_Documentation/files/CommandDefinition_execute.htm)
- [Fusion Feature Timeline](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Timeline.htm)
- [macOS UI scripting](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/AutomatetheUserInterface.html)
- [PyAutoGUI](https://pyautogui.readthedocs.io/en/latest/)
