#!/usr/bin/env python3
"""exCADmple: replay a COMPLETE phone stand through real macOS Fusion UI.

Not a Geometry Animation. PyAutoGUI moves the *real pointer*, opens Fusion's
NATIVE Extrude/Fillet dialogs, types parameters and confirms each operation.

Workflow:
  1. Run fusion_starter.py in Fusion to generate PhoneStand_STARTER.f3d.
  2. Keep the starter visible in Fusion; python3 mac_replay.py --teach
     (guided one-time calibration ALSO builds the stand).
  3. Reopen the untouched starter; python3 mac_replay.py --play.
  4. To repeat, reopen the starter again. Never save over it.

Limit: GUI coordinate replay depends on a stable layout/camera and the
sketches being selectable. It is not recovered from an arbitrary finished
model; the starter includes three genuine sketches, not solid bodies.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

CONFIG_DEFAULT = Path(__file__).with_name("fusion_native_points.json")
STEPS = (
    {"name": "01 Base plate", "target": "base_profile",
     "hotkey": "e", "field": "extrude_distance", "value": "8 mm"},
    {"name": "02 Back support", "target": "back_profile",
     "hotkey": "e", "field": "extrude_distance", "value": "6 mm"},
    {"name": "03 Front lip", "target": "lip_profile",
     "hotkey": "e", "field": "extrude_distance", "value": "5 mm"},
    {"name": "04 Finish edges", "target": "fillet_edge",
     "hotkey": "f", "field": "fillet_radius", "value": "2 mm"},
)

def preflight():
    if platform.system() != "Darwin":
        raise RuntimeError("Actual replay requires macOS and Autodesk Fusion Desktop.")
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError(
            "Missing PyAutoGUI. Run: python3 -m pip install pyautogui"
        ) from exc
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = .20
    return pyautogui


def activate_fusion():
    script = '''tell application "System Events"
        set matches to application processes whose name contains "Fusion"
        if (count of matches) = 0 then error "Fusion is not running"
        set p to item 1 of matches
        set frontmost of p to true
        return name of p
    end tell'''
    result = subprocess.run(["osascript", "-e", script], text=True,
                            capture_output=True)
    if result.returncode:
        raise RuntimeError("Cannot activate Fusion; give Terminal Accessibility "
                           "permission. " + result.stderr.strip())
    return result.stdout.strip()


def check_point(pg, coords):
    if not isinstance(coords, list) or len(coords) != 2 or not all(
        isinstance(n, int) for n in coords
    ):
        raise ValueError("Expected an [x,y] integer point, got %r" % coords)
    x, y = coords
    w, h = pg.size()
    if not (5 <= x < w - 5 and 5 <= y < h - 5):
        raise ValueError("Point %r outside primary display %s x %s. "
                         "Put Fusion on the primary screen and recalibrate." %
                         (coords, w, h))


def ask_point(pg, prompt):
    print("\n" + prompt)
    input("Move the pointer to that spot IN FUSION, then press Return IN TERMINAL: ")
    loc = pg.position()
    result = [int(loc.x), int(loc.y)]
    check_point(pg, result)
    print("Stored:", result)
    return result


def shot(path, label):
    if path is None:
        return
    path.mkdir(parents=True, exist_ok=True)
    output = path / (label + ".png")
    r = subprocess.run(["screencapture", "-x", str(output)], capture_output=True)
    if r.returncode:
        print("Could not capture screenshot", label, file=sys.stderr)


def select_and_start(pg, target, hotkey, delay):
    check_point(pg, target)
    activate_fusion()
    time.sleep(.4)
    pg.moveTo(target[0], target[1], duration=1.0)
    pg.click()
    time.sleep(.65 * delay)
    pg.press(hotkey)
    time.sleep(1.5 * delay)


def input_and_confirm(pg, field, value, delay, commit=True):
    check_point(pg, field)
    activate_fusion()
    time.sleep(.3)
    pg.moveTo(field[0], field[1], duration=.85)
    pg.click()
    pg.hotkey("command", "a")
    pg.write(value, interval=.115 * delay)
    time.sleep(.8 * delay)
    if commit:
        pg.press("enter")
        time.sleep(2.1 * delay)


def guide(pg, config_path, screenshots, delay, commit):
    print("""
exCADmple Fusion native UI calibration / first full replay
-----------------------------------------------------------
Open PhoneStand_STARTER.f3d freshly in Fusion, show all three sketches,
set an isometric camera and maximize Fusion on the primary display.
The four operations will actually modify this disposable document.
You MUST visually check each dialog and geometry. Ctrl-C or mouse to
upper-left stops the replay. The source starter file is never overwritten.
""")
    input("Press Return to BEGIN the guided replay (Ctrl-C to cancel): ")
    coords = {}
    for i, step in enumerate(STEPS):
        label = step["name"]
        print("\n========", label, "========")
        if i == 0:
            target_prompt = "Hover over the CENTER of the base sketch profile."
        elif i == 1:
            target_prompt = "Hover over the CENTER of the tall back-support sketch profile."
        elif i == 2:
            target_prompt = "Hover over the CENTER of the short front-lip sketch profile."
        else:
            target_prompt = "Hover over a suitable visible solid edge for the Fillet."
        coords[step["target"]] = ask_point(pg, target_prompt)
        select_and_start(pg, coords[step["target"]], step["hotkey"], delay)
        shot(screenshots, "%02d-native-dialog-open" % (i+1))
        if step["field"] not in coords:
            coords[step["field"]] = ask_point(
                pg, "Fusion should now show the NATIVE %s dialog. "
                    "Hover over the editable %s numeric FIELD." %
                    ("Extrude" if step["hotkey"] == "e" else "Fillet",
                     "Distance" if step["hotkey"] == "e" else "Radius"))
        print("Typing", step["value"], "into real Fusion dialog...")
        input_and_confirm(pg, coords[step["field"]], step["value"],
                          delay, commit=commit)
        shot(screenshots, "%02d-after-native-operation" % (i+1))
        if i < len(STEPS) - 1:
            print("Inspect the model. If wrong, CANCEL with Ctrl-C and reopen starter.")
            input("If it looks right, press Return to continue with next step: ")
    data = {"format": "excadmple-fusion-native-points", "version": 1,
            "steps": list(STEPS), "points": coords}
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("\nSaved replay coordinates:", config_path)
    print("The phone stand was built using REAL native Fusion commands.")
    print("Now REOPEN the untouched PhoneStand_STARTER.f3d and run --play.")


def load_config(config):
    data = json.loads(config.read_text(encoding="utf-8"))
    if data.get("format") != "excadmple-fusion-native-points":
        raise ValueError("Not an exCADmple Fusion calibration file")
    coords = data.get("points", {})
    for step in STEPS:
        if step["target"] not in coords or step["field"] not in coords:
            raise ValueError("Calibration missing " + step["target"])
    return coords


def dry_plan(config):
    coords = load_config(config)
    for i, step in enumerate(STEPS, 1):
        print("%d. %s: mouse to %s, press '%s', click field %s, type '%s', "
              "press Enter" % (
                  i, step["name"], coords[step["target"]], step["hotkey"],
                  coords[step["field"]], step["value"]))


def play(pg, config, screenshots, delay, commit):
    coords = load_config(config)
    for xy in coords.values():
        check_point(pg, xy)
    print("Native replay: four genuine Fusion modeling operations")
    print("WARNING: Works only with a FRESH starter and the SAME screen, "
          "viewport, workspace, and sketch visibility used for calibration.")
    input("Focus on disposable Fusion starter, then press Return to start: ")
    shot(screenshots, "00-fresh-starter")
    for i, step in enumerate(STEPS):
        print("Native command:", step["name"])
        select_and_start(pg, coords[step["target"]], step["hotkey"], delay)
        shot(screenshots, "%02d-dialog" % (i+1))
        input_and_confirm(pg, coords[step["field"]], step["value"],
                          delay, commit=commit)
        shot(screenshots, "%02d-result" % (i+1))
        if not commit:
            print("Stopped before confirmation. Inspect dialog or press Esc.")
            break
    if commit:
        print("Playback finished. Check all four operations in Fusion timeline.")
    else:
        print("Preview complete (only first command).")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    actions = p.add_mutually_exclusive_group(required=True)
    actions.add_argument("--teach", action="store_true",
                         help="Calibrate pointer positions while building full project.")
    actions.add_argument("--play", action="store_true",
                         help="Replay full project on newly opened original starter.")
    actions.add_argument("--dry-run", action="store_true")
    p.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    p.add_argument("--slow", type=float, default=1.0,
                   help="Delay multiplier, recommended 1.5 on slow Macs.")
    p.add_argument("--screenshots", action="store_true")
    p.add_argument("--stop-before-commit", action="store_true",
                   help="Only inspect the first native dialog; do not modify model.")
    args = p.parse_args(argv)
    if args.slow < 0.5 or args.slow > 6:
        p.error("--slow must be between 0.5 and 6")
    if args.dry_run:
        dry_plan(args.config)
        return
    pg = preflight()
    screenshots = Path(__file__).with_name("evidence") if args.screenshots else None
    if args.teach:
        guide(pg, args.config, screenshots, args.slow,
              commit=not args.stop_before_commit)
    else:
        play(pg, args.config, screenshots, args.slow,
             commit=not args.stop_before_commit)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print("Replay error:", exc, file=sys.stderr)
        sys.exit(1)
