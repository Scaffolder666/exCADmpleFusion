"""Generate a complete native .blend lesson for the exCADmple Blender add-on.

Usage:
blender --background --factory-startup --python blender_expert/build_demo_blend.py -- --output ~/Documents/exCADmple_phone_stand.blend

The .blend contains five teacher objects (read-only), a twelve-step
reconstructed CAD operation lesson and a separate empty learner scene area.
Open the file in Blender with the add-on enabled; press PLAY in the sidebar.
"""
import argparse
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
import excadmple_blender as expert


def main():
    args_list = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,
                        default=Path.home()/"Documents"/"exCADmple_phone_stand.blend")
    args = parser.parse_args(args_list)
    args.output = args.output.expanduser().resolve()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    scene = bpy.context.scene
    if scene is None:
        raise RuntimeError("Blender has no active scene")
    steps = expert.build_example(scene)
    scene["excadmple.origin"] = "Reconstructed training example, NOT original human mouse event data"
    # Keep user's own geometry separate. Never edit learner objects during playback.
    scene["excadmple.learner_space"] = "Existing scene objects are freely editable"
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output),check_existing=False)
    print("Saved",args.output,"with",steps,"replayable operations")
    print("Enable the exCADmple add-on, open the file, View3D > N > exCADmple > Play")


if __name__ == "__main__":
    main()
