"""Run ONLY with Blender's own Python in a separate background process.

blender --background --factory-startup --python compiler_cli.py -- \
  --spec lesson.json --output native_compiled.json
"""
import argparse
import sys
from pathlib import Path

if __name__=='__main__':
    root=Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    from native_tutorial.native_compiler import compile_lesson
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p=argparse.ArgumentParser()
    p.add_argument('--spec',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args(argv)
    compile_lesson(args.spec,args.output)
